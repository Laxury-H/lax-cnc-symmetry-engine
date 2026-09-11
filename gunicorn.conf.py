"""Deployment defaults for synchronous CAD analysis requests."""

# Sessions are held in process memory; multiple workers cannot share them.
workers = 1
worker_class = "sync"
timeout = 300
accesslog = "-"
errorlog = "-"
