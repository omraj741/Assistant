from dotenv import load_dotenv
load_dotenv()

import os
import re
import requests
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any
from aiohttp import ClientError
from langchain_core.tools import tool
from langchain.tools import ToolRuntime
import streamlit as st
from langchain_groq import ChatGroq
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from toolbox_langchain import ToolboxClient


TOOLBOX_URL = os.getenv("TOOLBOX_URL", "http://127.0.0.1:5000")
TOOLSET_NAME = "postgres-toolset"


@dataclass
class LocationContext:
    latitude: float | None = None
    longitude: float | None = None


_NOMINATIM_LOCK = threading.Lock()
_NOMINATIM_LAST_REQUEST = 0.0


_LOCATION_COMPONENT = st.components.v2.component(
    "browser_geolocation",
    html="<span id='location_status'>Checking browser location permission...</span>",
    js="""
export default function (component) {
  const { data, parentElement, setStateValue } = component
  const status = parentElement.querySelector("#location_status")
  if (!status) return

  if (data?.coordinates) {
    status.textContent = "Current location detected."
    return
  }
  if (data?.error) {
    status.textContent = "Location unavailable. You can ask about a city by name."
    return
  }
  if (data?.requestStarted) return
  setStateValue("requestStarted", true)

  if (!navigator.geolocation) {
    setStateValue("error", "Browser geolocation is not supported.")
    return
  }

  navigator.geolocation.getCurrentPosition(
    ({ coords }) => setStateValue("coordinates", {
      latitude: coords.latitude,
      longitude: coords.longitude,
    }),
    (error) => setStateValue("error", error.message),
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
  )
}
""",
)


@tool
def search_google(query: str) -> str:
    """Search Google using SearchApi and return the top results."""
    api_key = os.getenv("SEARCHAPI_API_KEY")
    if not api_key:
        raise RuntimeError("SEARCHAPI_API_KEY is missing from the environment")

    response = requests.get(
        "https://www.searchapi.io/api/v1/search",
        params={"engine": "google", "q": query, "api_key": api_key},
        timeout=30,
    )
    response.raise_for_status()

    results = response.json().get("organic_results", [])
    return "\n\n".join(
        f"{item.get('title', '')}\n{item.get('link', '')}\n{item.get('snippet', '')}"
        for item in results[:5]
    ) or "No organic results found."


def _get_weather_at_coordinates(latitude: float, longitude: float, place: str) -> str:
    weather_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,weather_code,wind_speed_10m"
            ),
            "timezone": "auto",
        },
        timeout=15,
    )
    weather_response.raise_for_status()
    weather_data = weather_response.json()
    current = weather_data["current"]
    units = weather_data.get("current_units", {})

    conditions = {
        0: "clear sky",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "depositing rime fog",
        51: "light drizzle",
        53: "moderate drizzle",
        55: "dense drizzle",
        56: "light freezing drizzle",
        57: "dense freezing drizzle",
        61: "slight rain",
        63: "moderate rain",
        65: "heavy rain",
        66: "light freezing rain",
        67: "heavy freezing rain",
        71: "slight snow",
        73: "moderate snow",
        75: "heavy snow",
        77: "snow grains",
        80: "slight rain showers",
        81: "moderate rain showers",
        82: "violent rain showers",
        85: "slight snow showers",
        86: "heavy snow showers",
        95: "thunderstorm",
        96: "thunderstorm with slight hail",
        99: "thunderstorm with heavy hail",
    }

    condition = conditions.get(current["weather_code"], "unknown conditions")
    return (
        f"Current weather for {place} at {current['time']}: {condition}, "
        f"{current['temperature_2m']}{units.get('temperature_2m', '°C')}, "
        f"feels like {current['apparent_temperature']}"
        f"{units.get('apparent_temperature', '°C')}, "
        f"humidity {current['relative_humidity_2m']}"
        f"{units.get('relative_humidity_2m', '%')}, "
        f"wind {current['wind_speed_10m']}"
        f"{units.get('wind_speed_10m', ' km/h')}, "
        f"precipitation {current['precipitation']}"
        f"{units.get('precipitation', ' mm')}."
    )


@st.cache_data(ttl=86400, max_entries=256)
def _get_city_name_from_coordinates(latitude: float, longitude: float) -> str | None:
    global _NOMINATIM_LAST_REQUEST

    latitude = round(latitude, 4)
    longitude = round(longitude, 4)
    with _NOMINATIM_LOCK:
        elapsed = time.monotonic() - _NOMINATIM_LAST_REQUEST
        if elapsed < 1:
            time.sleep(1 - elapsed)
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "zoom": 10,
                "addressdetails": 1,
                "accept-language": "en",
            },
            headers={"User-Agent": "New3-QnA-Bot/1.0"},
            timeout=15,
        )
        _NOMINATIM_LAST_REQUEST = time.monotonic()

    response.raise_for_status()
    address = response.json().get("address", {})
    city = next(
        (
            address[key]
            for key in ("city", "town", "village", "municipality", "borough", "county")
            if address.get(key)
        ),
        None,
    )
    if not city:
        return None

    parts = [city]
    for key in ("state", "country"):
        value = address.get(key)
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts)


def _get_city_from_coordinates(latitude: float, longitude: float) -> str:
    city_name = _get_city_name_from_coordinates(latitude, longitude)
    if not city_name:
        return "I couldn't determine a city name for your current location."
    return f"Your approximate city is {city_name}."


@tool
def get_weather(runtime: ToolRuntime[LocationContext, Any], city: str = "") -> str:
    """Get weather for a city, or the user's browser location when city is omitted."""
    city = city.strip()
    if city:
        location_response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=15,
        )
        location_response.raise_for_status()
        locations = location_response.json().get("results", [])
        if not locations:
            return f"No matching location found for '{city}'."
        location = locations[0]
        latitude = location["latitude"]
        longitude = location["longitude"]
        place = ", ".join(
            part
            for part in (location.get("name"), location.get("admin1"), location.get("country"))
            if part
        )
        return _get_weather_at_coordinates(latitude, longitude, place)

    location_context = runtime.context
    if (
        not isinstance(location_context, LocationContext)
        or location_context.latitude is None
        or location_context.longitude is None
    ):
        return "Current location is unavailable. Allow browser location access or provide a city."
    return _get_weather_at_coordinates(
        location_context.latitude,
        location_context.longitude,
        "your current location",
    )


def _is_weather_question(query: str) -> bool:
    return any(
        keyword in query.lower()
        for keyword in ("weather", "temperature", "temp", "outside", "rain", "wind", "humidity")
    )


def _asks_for_current_location(query: str) -> bool:
    lowered = query.lower()
    return any(
        phrase in lowered
        for phrase in (
            "what is my location",
            "what's my location",
            "my location",
            "where am i",
            "where am i located",
            "where is my location",
            "my current location",
            "current location",
            "what is current location",
            "what city am i in",
            "what is my city",
            "what's my city",
            "what is the name of my city",
            "which city am i in",
            "my loca"
        )
    )


def _is_current_location_followup(query: str, previous_assistant: str) -> bool:
    assistant_text = previous_assistant.lower()
    asked_for_city = any(
        phrase in assistant_text
        for phrase in (
            "which city",
            "what city",
            "city name",
            "tell me the city",
            "let me know the city",
        )
    )
    if not asked_for_city:
        return False

    lowered = query.lower()
    return any(
        phrase in lowered
        for phrase in (
            "same city",
            "city i am in",
            "city i'm in",
            "where i am",
            "same place",
            "my city",
        )
    ) or bool(re.search(r"\bhere\b", lowered))


def _asks_for_city_name(query: str) -> bool:
    lowered = query.lower()
    return any(
        phrase in lowered
        for phrase in ("what city", "which city", "city name", "name of my city")
    )


@st.cache_resource
def create_toolbox_client() -> ToolboxClient:
    return ToolboxClient(TOOLBOX_URL)


@st.cache_resource
def create_qna_agent():
    postgres_tools = create_toolbox_client().load_toolset(TOOLSET_NAME)
    return create_agent(
        model=ChatGroq(model="openai/gpt-oss-20b"),
        tools=[search_google, get_weather, *postgres_tools],
        checkpointer=MemorySaver(),
        context_schema=LocationContext,
        system_prompt=(
            "You are a helpful assistant that can search Google and provide current weather "
            "using the weather tool. For weather requests without a named city, call get_weather "
            "without a city so it uses the user's browser location. Ask for a city only if current "
            "location is unavailable. Never invent weather conditions. For PostgreSQL questions, "
            "use the execute_sql tool and PostgreSQL syntax. Never claim a database operation "
            "succeeded unless the tool confirms it. Before destructive operations, explain the "
            "effect and ask the user to confirm."
        ),
    )


st.title("I'm your personal assistant")
st.caption("PostgreSQL requests use MCP Toolbox; keep the Toolbox server running.")

_LOCATION_KEY = "browser_location"
_location_state = st.session_state.get(_LOCATION_KEY, {})
_location_result = _LOCATION_COMPONENT(
    key=_LOCATION_KEY,
    data={
        "coordinates": _location_state.get("coordinates"),
        "error": _location_state.get("error"),
        "requestStarted": _location_state.get("requestStarted", False),
    },
    on_coordinates_change=lambda: None,
    on_error_change=lambda: None,
    on_requestStarted_change=lambda: None,
    height="content",
)
_coordinates = _location_result.coordinates or _location_state.get("coordinates")
if isinstance(_coordinates, dict):
    city_name = _get_city_name_from_coordinates(
        _coordinates["latitude"],
        _coordinates["longitude"],
    )
    if city_name:
        st.caption(
            f"Browser location detected: {city_name}. "
            "Coordinates are sent to OpenStreetMap Nominatim to find the city; "
            "Open-Meteo is used when you ask for weather."
        )
    else:
        st.caption(
            "Browser location detected, but the city name is unavailable. "
            "Coordinates are sent to OpenStreetMap Nominatim to find the city; "
            "Open-Meteo is used when you ask for weather."
        )
elif _location_state.get("error"):
    st.warning(
        f"Browser location unavailable: {_location_state['error']}. "
        "Allow location access or include a city in your question."
    )
else:
    st.caption(
        "Waiting for browser location permission. This requires localhost or HTTPS; "
        "coordinates are sent to Open-Meteo for weather."
    )

if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

for message in st.session_state.messages:
    st.chat_message(message["role"]).markdown(message["content"])

query = st.chat_input("Ask me anything:")
if query:
    previous_assistant = next(
        (
            message["content"]
            for message in reversed(st.session_state.messages)
            if message["role"] == "assistant"
        ),
        "",
    )
    st.session_state.messages.append({"role": "user", "content": query})
    st.chat_message("user").markdown(query)

    if _asks_for_city_name(query) and isinstance(_coordinates, dict):
        answer = _get_city_from_coordinates(
            _coordinates["latitude"],
            _coordinates["longitude"],
        )
    elif _asks_for_current_location(query) or _is_current_location_followup(
        query,
        previous_assistant,
    ):
        if isinstance(_coordinates, dict):
            answer = _get_city_from_coordinates(
                _coordinates["latitude"],
                _coordinates["longitude"],
            )
        else:
            answer = (
                "I don't have your location yet. Allow location access in your browser, "
                "or include a city in your question."
            )
    elif _is_weather_question(query) and not re.search(
        r"\b(?:in|for|near|at)\s+[a-z]",
        query,
        flags=re.IGNORECASE,
    ):
        if isinstance(_coordinates, dict):
            answer = _get_weather_at_coordinates(
                _coordinates["latitude"],
                _coordinates["longitude"],
                "your current location",
            )
        else:
            answer = (
                "I can't access your current location yet. Allow location access in your "
                "browser, or ask about a city by name."
            )
    else:
        try:
            agent = create_qna_agent()
        except ClientError as error:
            st.error(
                f"Could not load tools from MCP Toolbox at {TOOLBOX_URL}. "
                "Start the Toolbox server and try again. "
                f"Details: {error}"
            )
            st.stop()

        result = agent.invoke(
            {"messages": [{"role": "user", "content": query}]},
            {"configurable": {"thread_id": st.session_state.thread_id}},
            context=LocationContext(
                latitude=_coordinates.get("latitude") if isinstance(_coordinates, dict) else None,
                longitude=_coordinates.get("longitude") if isinstance(_coordinates, dict) else None,
            ),
        )
        answer = result["messages"][-1].content

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.chat_message("assistant").markdown(answer)