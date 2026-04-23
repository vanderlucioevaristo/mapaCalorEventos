from setuptools import setup, find_packages

setup(
    name="mapaCalorEventos",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "pydantic",
        "pandas",
        "pytest",
        "folium",
        "Authlib",
        "itsdangerous",
        "httpx",
        "python-dotenv",
    ],
)
