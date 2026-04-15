"""FastAPI service for Nebula Civitas.

Single process, multiple routers. Imports from domain packages (voting,
preferences, ...); domain packages never import from here.
"""
