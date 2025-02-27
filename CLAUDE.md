# CLAUDE.md - AI Server Agent Guidelines

## Commands
- Run server: `python app.py`
- Run tests: `python -m unittest tests/test_app.py`
- Run specific test: `python -m unittest tests.test_app.FlaskAppTests.test_root_route`

## Code Style
- **Imports**: Group standard library, third-party, and local imports
- **Formatting**: Use 4-space indentation, 79-character line length
- **Error Handling**: Use try/except blocks with specific error types and proper logging
- **Logging**: Use the logging module with appropriate levels (info, error, debug)
- **Database**: Use connection pooling with proper resource cleanup in finally blocks
- **Functions**: Include docstrings for all public functions
- **API Design**: Follow RESTful patterns with consistent JSON responses
- **Naming**: snake_case for variables/functions, PascalCase for classes
- **Comments**: Use section headers (# === SECTION X: TITLE ===) for code organization

## Architecture
This Flask server provides a Gemini AI interface for a Roblox game with Postgres database integration. Maintain separation between API routes, database utilities, and AI model interactions.