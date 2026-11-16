from dotenv import load_dotenv
load_dotenv()

import os
import requests
import uuid
from langchain_core.tools import tool
import streamlit as st
from langchain_groq import ChatGroq
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver


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


@tool
def get_weather(city: str) -> str:
    """Get weather for a given city."""
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
    weather_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": location["latitude"],
            "longitude": location["longitude"],
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
    place = ", ".join(
        part
        for part in (location.get("name"), location.get("admin1"), location.get("country"))
        if part
    )
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


@st.cache_resource
def create_qna_agent():
    return create_agent(
        model=ChatGroq(model="openai/gpt-oss-20b"),
        tools=[search_google, get_weather],
        checkpointer=MemorySaver(),
        system_prompt=(
            "You are a helpful assistant that can search Google and provide current weather "
            "using the weather tool. Ask for the city or location if it is missing. "
            "Never invent weather conditions; report tool errors clearly."
        ),
    )


agent = create_qna_agent()

st.title("I'm your personal assistant")
# st.markdown("Ask questions and let the assistant search Google when needed.")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

for message in st.session_state.messages:
    st.chat_message(message["role"]).markdown(message["content"])

query = st.chat_input("Ask me anything:")
if query:
    st.session_state.messages.append({"role": "user", "content": query})
    st.chat_message("user").markdown(query)

    result = agent.invoke(
        {"messages": [{"role": "user", "content": query}]},
        {"configurable": {"thread_id": st.session_state.thread_id}},
    )
    answer = result["messages"][-1].content

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.chat_message("assistant").markdown(answer)

