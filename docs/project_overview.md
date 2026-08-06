# PoshCopier - Project Overview

## Purpose

PoshCopier is a Python desktop application designed to automate the process of copying fashion listings from one Poshmark account (source) to another Poshmark account (destination). It scrapes listing details, downloads images, and re-publishes them to the destination account.

## Key Features

- **Automated Listing Discovery**: Discovers available listings from a source Poshmark closet
- **Web Scraping**: Extracts listing details including title, description, brand, price, size, category, colors, and condition
- **Image Management**: Downloads and manages listing images locally
- **Duplicate Detection**: Prevents re-uploading listings that already exist in the destination closet
- **Automated Publishing**: Fills out and publishes listing forms on the destination Poshmark account
- **Pipeline Control**: Pause, resume, and stop operations mid-process
- **Inventory Management**: Track downloaded listings and their upload status
- **Recovery Tools**: Identify and repair broken listing folders
- **GUI Dashboard**: Tkinter-based interface for monitoring and controlling the pipeline
- **Dry Run Mode**: Test the pipeline without actually publishing listings
- **Resume Capability**: Continue interrupted pipeline runs from where they left off

## Technology Stack

- **Language**: Python 3.x with type hints (`from __future__ import annotations`)
- **GUI Framework**: Tkinter (standard library)
- **Web Automation**: Playwright (Chromium browser automation)
- **Database**: SQLite3 (tracking copied listings)
- **Build Tool**: PyInstaller (packaging into standalone executables)
- **Data Format**: JSON for configuration and listing storage

## Target Platform

- **Primary**: Windows 11
- **Shell**: PowerShell
- **Distribution**: Standalone executables (PoshCopier.exe and PoshCopierPipeline.exe)

## Project Structure

```
PoshCopier/
├── app.py                    # Main dashboard entry point
├── pipeline_entry.py         # Pipeline process entry point
├── run_pipeline.py           # Core pipeline orchestration logic
├── run_single_listing.py     # Single listing upload utility
├── login.py                  # Poshmark authentication management
├── build.py                  # PyInstaller build script
├── runtime_paths.py          # Path resolution for dev/packaged modes
├── pipeline_control.py       # Pipeline pause/resume/stop controls
├── resume_state.py           # Pipeline resume state management
├── dashboard/                # Dashboard UI components
├── scraper/                  # Web scraping modules
├── uploader/                 # Listing upload automation
├── inventory/                # Inventory management and health checks
├── data/database/            # SQLite database utilities
├── gui/                      # Legacy GUI components (CustomTkinter)
├── assets/                   # Icons and images
└── docs/                     # Project documentation
```

## Runtime Directories

The application creates and manages these directories at runtime:

- **downloads/**: Stores scraped listings (JSON + images) organized by listing ID
- **logs/**: Pipeline logs, control state, and resume state
- **logs/errors/**: Error logs and stack traces
- **pw-browsers/**: Playwright browser binaries

## Authentication

PoshCopier uses Playwright's storage state feature to persist login sessions:

- **source_state.json**: Authentication for the source Poshmark account
- **destination_state.json**: Authentication for the destination Poshmark account

Users run [`login.py`](../login.py) to save their login sessions before using the pipeline.

## Database

A SQLite database ([`poshcopier.db`](../data/database/database.py)) tracks which listings have been copied to prevent duplicates:

- **Table**: `copied_listings`
- **Columns**: `id`, `source_listing_id`, `destination_listing_id`, `title`, `copied_at`

## Execution Modes

1. **Development Mode**: Run Python scripts directly
2. **Packaged Mode**: Run standalone executables built with PyInstaller
   - **PoshCopier.exe**: Dashboard application
   - **PoshCopierPipeline.exe**: Background pipeline process

## Pipeline Workflow

1. **Discovery**: Scan source closet for available listings
2. **Scraping**: Extract listing details and download images
3. **Validation**: Check for duplicates and verify data completeness
4. **Upload**: Navigate to Poshmark's create-listing page and fill form fields
5. **Publishing**: Submit the listing to the destination account
6. **Recording**: Mark listing as copied in the database

## User Interface

The dashboard provides:

- **Pipeline Tab**: Configure and run the pipeline with real-time progress monitoring
- **Inventory Tab**: Browse downloaded listings, view thumbnails, and manage inventory health
- **Run Settings**: Mode (dry run/live), listing count, retry configuration
- **Controls**: Start, pause, resume, stop after current
- **Status Display**: Current listing, progress percentage, statistics
- **Activity Log**: Real-time pipeline output and events
