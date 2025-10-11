# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TikLocal is a Flask-based web application that provides a TikTok-like interface for browsing local media files. It serves as a local media server combining features of TikTok and Pinterest for videos and images.

## Key Dependencies

- **Backend**: Flask 3.1.0, Waitress (WSGI server), PyYAML 6.0 (config file support)
- **Frontend**: TailwindCSS v4, Feather Icons, Hammer.js
- **Python**: Requires Python >=3.10,<4.0
- **Package Management**: Poetry for Python dependencies, npm for CSS building

## Common Development Commands

### CSS Development
```bash
# Watch mode for development (rebuilds CSS on changes)
npm run dev
# or
npm run build-css

# Production build (minified CSS)
npm run build
# or  
npm run build-css-prod
```

### Python Development
```bash
# Install dependencies
poetry install

# Run the application (multiple ways)
poetry run tiklocal /path/to/media/folder       # Direct path argument
poetry run tiklocal --port 9000                 # Custom port with config file
MEDIA_ROOT=/path tiklocal                       # Environment variable
tiklocal                                        # Use config file

# Configuration file (optional)
# Create ~/.config/tiklocal/config.yaml:
# media_root: /path/to/media
# host: 0.0.0.0
# port: 8000

# Get help
tiklocal --help
```

## Architecture

### Core Application Structure

- **`tiklocal/app.py`**: Main Flask application factory with all routes and view functions
- **`tiklocal/run.py`**: CLI entry point with argument parsing, config file loading, and Waitress server startup
- **`tiklocal/config.py`**: Configuration file (currently empty, configuration handled via config file/env vars)

### Key Routes and Features

- **`/`** (tiktok.html): TikTok-like vertical scrolling video interface with random shuffle
- **`/browse`**: Paginated video browser with file management capabilities
- **`/gallery`**: Pinterest-style image gallery with directory navigation
- **`/settings`**: Application settings and statistics
- **`/detail/<name>`**: Individual video detail view with navigation
- **`/favorite`**: Favorited media management using JSON storage
- **`/media/<name>`** and **`/media2`**: Media file serving endpoints

### Frontend Structure

- **Templates**: Located in `tiklocal/templates/` using Jinja2
- **CSS**: TailwindCSS v4 with custom theme including dark mode support
- **JavaScript**: Vanilla JS with Feather icons and Hammer.js for touch gestures
- **Theme System**: Light/dark mode toggle with localStorage persistence

### Media Management

- **Storage**: Files stored in `MEDIA_ROOT` environment variable location
- **Supported Formats**: MP4, WebM videos; various image formats
- **File Operations**: Delete functionality, favorite management via JSON
- **Navigation**: Recursive directory scanning with mtime-based sorting

### Configuration

The application supports multiple configuration methods with the following priority (highest to lowest):

1. **Command Line Arguments**: Direct arguments passed to `tiklocal`
   - `tiklocal /path/to/media` - specify media root
   - `--host HOST` - server host (default: 0.0.0.0)
   - `--port PORT` - server port (default: 8000)

2. **Environment Variables**:
   - `MEDIA_ROOT` - path to media directory
   - `TIKLOCAL_HOST` - server host
   - `TIKLOCAL_PORT` - server port

3. **Configuration File**: `~/.config/tiklocal/config.yaml` or `~/.tiklocal/config.yaml`
   ```yaml
   media_root: /path/to/media
   host: 0.0.0.0
   port: 8000
   ```

4. **Defaults**: host=0.0.0.0, port=8000

- **Instance Config**: Uses Flask's instance-relative configuration
- **Favorites**: Stored as JSON file in media root directory

## Development Notes

- Configuration priority: CLI args > Environment variables > Config file > Defaults
- Config file locations: `~/.config/tiklocal/config.yaml` or `~/.tiklocal/config.yaml`
- Templates include responsive design optimized for mobile and tablet usage
- Custom Jinja2 filters for timestamp and file size formatting
- Error handling includes user-friendly messages and proper HTTP status codes
- Dark mode implementation uses CSS custom properties and data attributes

## Release Process

When publishing a new version to PyPI:

1. **Update version number** in `pyproject.toml`:
   ```toml
   version = "x.y.z"
   ```

2. **Commit changes**:
   ```bash
   git add .
   git commit -m "Release vx.y.z: description of changes"
   ```

3. **Create and push git tag** (required for PyPI build):
   ```bash
   git tag -a vx.y.z -m "Release vx.y.z: description"
   git push origin vx.y.z
   ```

4. **Push commits**:
   ```bash
   git push
   ```

**Note**: The git tag triggers the CI/CD pipeline to automatically build and publish to PyPI.