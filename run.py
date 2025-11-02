"""
Quick start script for development and production
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))  # Railway sets PORT automatically
    host = "0.0.0.0"  # Listen on all interfaces in production

    print("=" * 60)
    print("Starting ConnectHub Server...")
    print("=" * 60)
    print(f"\nServer will be available at: http://{host}:{port}")
    print("Press Ctrl+C to stop the server\n")
    print("=" * 60)
    print()

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )
