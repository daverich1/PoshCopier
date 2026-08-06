# PoshCopier - Roadmap

## Current State

PoshCopier is a functional desktop application that automates copying Poshmark listings from a source account to a destination account. The core pipeline works reliably with the following features:

### Implemented Features

- ✅ Web scraping of Poshmark listings using Playwright
- ✅ Automated listing discovery from source closet
- ✅ Image downloading and local storage
- ✅ Automated form filling and publishing to destination account
- ✅ Duplicate detection to prevent re-uploading
- ✅ SQLite database tracking of copied listings
- ✅ Tkinter-based dashboard GUI
- ✅ Pipeline control (pause, resume, stop after current)
- ✅ Resume capability for interrupted runs
- ✅ Dry run mode for testing
- ✅ Inventory management and browsing
- ✅ Inventory health checks and validation
- ✅ Recovery tools for broken listing folders
- ✅ Thumbnail generation and caching
- ✅ Real-time progress monitoring
- ✅ Activity log viewer
- ✅ Error logging and stack traces
- ✅ PyInstaller packaging for Windows
- ✅ Multi-size inventory support
- ✅ Configurable retry logic

## Known Issues and Technical Debt

### Code Organization

- **Duplicate GUI implementations**: Both [`dashboard/`](../dashboard/) (Tkinter) and [`gui/`](../gui/) (CustomTkinter) directories exist
  - The [`dashboard/`](../dashboard/) implementation is actively used
  - The [`gui/`](../gui/) directory appears to be legacy/experimental code
  - **Action**: Consider removing or consolidating the [`gui/`](../gui/) directory

- **Empty files**: [`models.py`](../models.py) and [`config.py`](../config.py) are empty
  - **Action**: Remove if unused, or document their intended purpose

- **Hardcoded values**: Destination closet URL is hardcoded in [`run_pipeline.py`](../run_pipeline.py)
  - `DESTINATION_CLOSET_URL = "https://poshmark.com/closet/dveshop"`
  - **Action**: Move to configuration file or make user-configurable

### Robustness

- **Selector brittleness**: Web scraping relies on CSS selectors that may break if Poshmark updates their UI
  - Multiple fallback selectors help, but maintenance is ongoing
  - **Action**: Implement automated tests to detect selector breakage

- **Error recovery**: Some error scenarios may leave the pipeline in an inconsistent state
  - **Action**: Improve error handling and state cleanup

- **Browser crashes**: Playwright browser crashes are not always handled gracefully
  - **Action**: Add browser health checks and automatic restart

### Performance

- **Sequential processing**: Listings are processed one at a time
  - **Action**: Consider parallel processing for scraping (with rate limiting)

- **Thumbnail generation**: Thumbnails are generated on-demand, which can be slow
  - **Action**: Pre-generate thumbnails in background thread

- **Large inventory**: Loading thousands of listings can be slow
  - **Action**: Implement pagination or lazy loading in inventory panel

### User Experience

- **Configuration UI**: No GUI for configuring settings like destination closet URL
  - **Action**: Add settings panel to dashboard

- **Progress persistence**: Progress bars reset when dashboard is closed
  - **Action**: Save and restore progress state

- **Listing preview**: No way to preview a listing before upload
  - **Action**: Add preview dialog in inventory panel

## Potential Enhancements

### High Priority

1. **Configuration Management**
   - Move hardcoded values to configuration file
   - Add settings panel in dashboard
   - Support multiple destination accounts
   - Configurable scraping delays and timeouts

2. **Improved Error Handling**
   - Better error messages for common failures
   - Automatic retry with exponential backoff
   - Graceful handling of browser crashes
   - Network error detection and recovery

3. **Code Cleanup**
   - Remove or consolidate duplicate GUI code
   - Remove empty/unused files
   - Refactor large functions (e.g., [`run_pipeline.py`](../run_pipeline.py) main function is 1000+ lines)
   - Add comprehensive docstrings

4. **Testing Infrastructure**
   - Unit tests for core logic
   - Integration tests for scraping
   - Mock Poshmark responses for testing
   - Automated selector validation

### Medium Priority

5. **Enhanced Inventory Management**
   - Bulk operations (delete, re-upload, export)
   - Search and filter listings
   - Sort by various fields
   - Export inventory to CSV/Excel
   - Import listings from CSV

6. **Scheduling and Automation**
   - Schedule pipeline runs
   - Automatic discovery of new listings
   - Batch processing modes
   - Watchdog for new listings

7. **Analytics and Reporting**
   - Success/failure statistics
   - Upload history
   - Performance metrics
   - Export reports

8. **Multi-Account Support**
   - Support multiple source accounts
   - Support multiple destination accounts
   - Account switching in GUI
   - Per-account configuration

### Low Priority

9. **Advanced Features**
   - Price adjustment rules (e.g., +10% markup)
   - Title/description templates and transformations
   - Category mapping rules
   - Automatic tagging
   - Image editing (watermarks, cropping)

10. **Cross-Platform Support**
    - macOS support
    - Linux support
    - Platform-specific packaging

11. **Cloud Integration**
    - Cloud storage for listings
    - Remote monitoring
    - Multi-machine coordination

12. **API Integration**
    - If Poshmark provides an API, migrate from web scraping
    - More reliable and maintainable
    - Faster processing

## Architecture Improvements

### Refactoring Opportunities

1. **Separate concerns in [`run_pipeline.py`](../run_pipeline.py)**
   - Extract pipeline orchestration logic
   - Create separate classes for scraping, uploading, and coordination
   - Improve testability

2. **Dependency injection**
   - Pass dependencies explicitly rather than importing globals
   - Makes testing easier
   - Improves modularity

3. **Event-driven architecture**
   - Use event bus for dashboard communication
   - Decouple components
   - Enable plugins/extensions

4. **State machine for pipeline**
   - Formalize pipeline states (idle, running, paused, stopped, error)
   - Clear state transitions
   - Better error recovery

### Technology Upgrades

1. **Modern GUI framework**
   - Consider migrating to PyQt6 or PySide6 for better UI capabilities
   - Or use web-based UI (Electron, Tauri, or local web server)

2. **Async/await**
   - Use `asyncio` and Playwright's async API
   - Better concurrency
   - More efficient resource usage

3. **Database ORM**
   - Use SQLAlchemy or similar for database operations
   - Type-safe queries
   - Easier migrations

4. **Configuration library**
   - Use `pydantic` for configuration validation
   - Type-safe settings
   - Environment variable support

## Security Enhancements

1. **Credential encryption**
   - Encrypt stored authentication tokens
   - Use OS keyring for sensitive data

2. **Rate limiting**
   - Respect Poshmark's rate limits
   - Avoid account suspension
   - Configurable delays between requests

3. **Input validation**
   - Validate all user inputs
   - Sanitize file paths
   - Prevent injection attacks

## Documentation Improvements

1. **User documentation**
   - Installation guide
   - Quick start tutorial
   - Troubleshooting guide
   - FAQ

2. **Developer documentation**
   - Contributing guidelines
   - Development setup
   - Architecture deep-dives
   - API reference

3. **Video tutorials**
   - Screen recordings of common workflows
   - Setup and configuration
   - Troubleshooting common issues

## Maintenance Tasks

### Regular Maintenance

- Monitor Poshmark UI changes and update selectors
- Update dependencies (Playwright, Python packages)
- Test on new Windows versions
- Review and triage user-reported issues
- Update documentation

### Code Quality

- Run linters (pylint, flake8, mypy)
- Format code consistently (black, isort)
- Remove dead code
- Update type hints
- Add missing docstrings

## Migration Path

If considering major refactoring:

1. **Phase 1**: Stabilize current implementation
   - Fix critical bugs
   - Add tests for core functionality
   - Document current behavior

2. **Phase 2**: Incremental improvements
   - Refactor one module at a time
   - Maintain backward compatibility
   - Add tests before refactoring

3. **Phase 3**: Architecture evolution
   - Introduce new patterns gradually
   - Migrate to new GUI framework if needed
   - Maintain feature parity

## Community and Ecosystem

### Potential Expansions

- Support for other resale platforms (eBay, Mercari, Depop)
- Plugin system for custom transformations
- Marketplace for listing templates
- Community-contributed selectors and rules

### Open Source Considerations

If open-sourcing:
- Remove hardcoded personal information
- Add license file
- Create contribution guidelines
- Set up issue templates
- Add CI/CD pipeline
- Create public roadmap

## Success Metrics

Track these metrics to measure improvements:

- **Reliability**: Success rate of listing uploads
- **Performance**: Listings processed per hour
- **Stability**: Mean time between failures
- **Usability**: Time to complete common tasks
- **Maintainability**: Time to fix bugs or add features

## Conclusion

PoshCopier is a functional and useful tool with room for improvement. The roadmap prioritizes stability, code quality, and user experience enhancements. The modular architecture allows for incremental improvements without major rewrites.

Focus areas:
1. **Short term**: Fix known issues, improve error handling, clean up code
2. **Medium term**: Enhance features, improve performance, add tests
3. **Long term**: Consider architectural improvements and platform expansion
