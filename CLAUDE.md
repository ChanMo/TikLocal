# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TikLocal is a Flask-based web application that provides a TikTok-like interface for browsing local media files. It serves as a local media server combining features of TikTok and Pinterest for videos and images.

## Key Dependencies

- **Backend**: Flask 3.1.0, Waitress (WSGI server)
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

# Run the application
poetry run tiklocal /path/to/media/folder

# Or run directly
python -m tiklocal.run
```

## Architecture

### Core Application Structure

- **`tiklocal/app.py`**: Main Flask application factory with all routes and view functions
- **`tiklocal/run.py`**: Entry point that starts the Waitress WSGI server on port 8000
- **`tiklocal/config.py`**: Configuration file (currently empty, uses environment variables)

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

- **Environment Variables**: `MEDIA_ROOT` (required) - path to media directory
- **Instance Config**: Uses Flask's instance-relative configuration
- **Favorites**: Stored as JSON file in media root directory

## Development Notes

- The application uses environment variable `MEDIA_ROOT` to determine media location
- Templates include responsive design optimized for mobile and tablet usage
- Custom Jinja2 filters for timestamp and file size formatting
- Error handling includes user-friendly messages and proper HTTP status codes
- Dark mode implementation uses CSS custom properties and data attributes