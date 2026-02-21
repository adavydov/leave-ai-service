# Recommended Gunicorn settings for Render/containers.
# Enables full stdout/stderr capture and access/error logs for debugging.

bind = "0.0.0.0:10000"
worker_class = "uvicorn.workers.UvicornWorker"
workers = 1
threads = 4
timeout = 180

accesslog = "-"
errorlog = "-"
loglevel = "info"
capture_output = True

# Keep output unbuffered for real-time diagnostics.
enable_stdio_inheritance = True
