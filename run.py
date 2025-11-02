"""
Quick start script for development
"""
import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("Starting ConnectHub Server...")
    print("=" * 60)
    print("\nServer will be available at: http://localhost:8080")
    print("Press Ctrl+C to stop the server\n")
    print("=" * 60)
    print()
    
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8080,
        reload=False,
        log_level="info"
    )

