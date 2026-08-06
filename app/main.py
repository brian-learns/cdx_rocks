from fastapi import FastAPI

# Initialize the FastAPI application
app = FastAPI(title="Minimal Test App", description="A lightweight API built with FastAPI and uv", version="1.0.0")


@app.get("/")
def read_root():
    """
    Root endpoint returning a simple welcome message.
    """
    return {"message": "Hello from FastAPI running inside a lean Docker container!"}


@app.get("/health")
def health_check():
    """
    Standard health check endpoint for Docker, Kubernetes, or cloud platform probes.
    """
    return {"status": "healthy", "database": "connected"}


@app.get("/hello/{name}")
def greet_user(name: str):
    """
    Dynamic path parameter endpoint.
    """
    return {"message": f"Hello, {name}!"}
