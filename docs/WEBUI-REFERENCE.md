---
template-id: T-WUI
template-version: 1.0
applies-to: docs/WEBUI-REFERENCE.md
registry: service
required: conditional
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: platform-standards

project: expert-agent-mcp-server
doc-last-updated: 2026-06-12
doc-git-commit: 23792217e632a149847f4be56af53e9b6b744c14
doc-git-branch: main
doc-source-shas: []
doc-age-policy: 90d
doc-conformance-stamp: 2026-06-12T12:00:00Z
---

# expert-agent-mcp-server — WEBUI-REFERENCE

> **Template version:** T-WUI v1.0 — conditional: service has a WebUI panel.

## 1. Panel structure
Routes, panels, navigation, role gating.

| Route | Panel | Roles | Backend route |
|---|---|---|---|

## 2. Login
Flow (cookie vs api_key vs bootstrap), session storage, logout.

## 3. RBAC visibility matrix
**You MUST include:** what each role sees / can do per panel.

| Panel | admin | read-write | read-only | other |
|---|---|---|---|---|

## 4. Static routes
List of static UI routes registered in `_SPA_ENTRY_ROUTES` (see AGENT-LESSONS for the anon-gate trap).

## 5. Cross-references
- [API-REFERENCE.md](API-REFERENCE.md)
- [ROLES-AND-USECASES.md](ROLES-AND-USECASES.md)
- PS-77-webui-comprehensive.md
- PS-30-ui.md

## 6. Project-specific notes



<!-- W28C-1710a recovery: full content from archive/2026-06-12/WEB_UI.md (archived sha256=01e4ea535da7, 713 lines) -->

## Recovered domain content — `archive/2026-06-12/WEB_UI.md` (713 lines)

_This section carries forward the full content of the archived predecessor doc verbatim. Topic checklist + SHA256 chain in `cloud-dog-ai-platform-standards/working/evidence/W28C-1710a/per-doc/expert-agent-mcp-server/WEB_UI.md.topics.tsv`. Archive contents are unchanged (sha256 stable)._

# Web UI Server Documentation
**Version:** 0.1 • 2025-01-XX

## Overview

The Web UI Server provides a chat interface and administration dashboard for the Expert Agent MCP Server. It offers a user-friendly interface for interacting with expert assistants and managing the system.

**Port:** 8080 (configurable via `CLOUD_DOG__EXPERT__WEB_SERVER__PORT`)

## Quick Start

### Running the Web UI Server

```bash
# Using server control script (recommended)
./server_control.sh start web

# Or manually (development only)
python3 start_web_server.py
```

### Accessing the Web UI

Open your browser and navigate to:
```
http://localhost:8080
```

### Configuration

Web UI Server configuration is loaded from:
1. Environment Variables (`CLOUD_DOG__EXPERT__*`)
2. `.env` file
3. `config.yaml`
4. `default.yaml`

**Key Configuration Options:**
```bash
CLOUD_DOG__EXPERT__WEB_SERVER__PORT=8080
CLOUD_DOG__EXPERT__WEB_SERVER__HOST=0.0.0.0
CLOUD_DOG__EXPERT__API_SERVER__URL=http://localhost:8083
```

## Key Features

### 1. Chat Interface
- Interactive conversation with expert assistants
- Session management
- Conversation history
- Real-time message updates

### 2. Administration Dashboard
- Expert configuration management
- User and group management
- System monitoring and status
- Knowledge base management

### 3. UI Components
- Responsive design
- Modern, intuitive interface
- Keyboard shortcuts
- Mobile access support

## Architecture

### Components

- **Web Server**: HTTP server (FastAPI/Flask)
- **Frontend**: HTML/CSS/JavaScript
- **API Integration**: Communication with API Server
- **WebSocket Client**: Real-time updates via A2A Server

### Data Flow

```
Browser
  ↓
Web UI Server
  ↓
API Server (REST)
  ↓
A2A Server (WebSocket for real-time)
  ↓
Response
  ↓
Browser
```

## Protocol/Interface Details

### HTTP Endpoints

#### Static Files
- `GET /` - Main application page
- `GET /static/*` - Static assets (CSS, JS, images)
- `GET /favicon.ico` - Favicon

#### API Proxy
- Web UI proxies API requests to API Server
- Authentication handled via session cookies

### WebSocket Integration

- Real-time updates via A2A Server
- Session event streaming
- Message updates

## Key Flows

### Chat Flow
```
User opens chat interface
  ↓
Create or resume session
  ↓
Send message
  ↓
Display response
  ↓
Update conversation history
```

### Administration Flow
```
Admin accesses dashboard
  ↓
View system status
  ↓
Manage configurations
  ↓
Update settings
```

## Usage Examples

### Chat Interface
1. Navigate to `http://localhost:8080`
2. Select expert configuration
3. Start conversation
4. Send messages and receive responses
5. View conversation history

### Administration
1. Navigate to admin dashboard
2. View system status
3. Manage expert configurations
4. Manage users and groups
5. Monitor system health

## Configuration

### Environment Variables

```bash
CLOUD_DOG__EXPERT__WEB_SERVER__PORT=8080
CLOUD_DOG__EXPERT__WEB_SERVER__HOST=0.0.0.0
CLOUD_DOG__EXPERT__API_SERVER__URL=http://localhost:8083
CLOUD_DOG__EXPERT__A2A_SERVER__URL=ws://localhost:8082
```

See [PARAMETERS.md](PARAMETERS.md) for complete configuration reference.

## Startup & Deployment

### Development
```bash
./server_control.sh start web
```

### Production
- Use `server_control.sh` for service management
- Ensure API Server and A2A Server are accessible
- Configure static file serving
- Set up reverse proxy if needed

## UI Components

### Chat Interface
- Message input area
- Conversation display
- Session selector
- Expert configuration selector

### Administration Dashboard
- System status panel
- Expert configuration panel
- User management panel
- Group management panel
- Knowledge base panel

### Keyboard Shortcuts
- `Ctrl+Enter` - Send message
- `Ctrl+K` - Focus search
- `Esc` - Close modal/dialog

## Mobile Access

- Responsive design
- Touch-friendly interface
- Mobile-optimized layout
- Offline capability (if implemented)

## Error Handling

### Error Display
- User-friendly error messages
- Error logging
- Retry mechanisms
- Fallback UI states

### Common Errors
- API Server unavailable
- Session not found
- Authentication failed
- Network errors

## Performance

### Optimization
- Static file caching
- API response caching
- Lazy loading
- Code splitting

### Benchmarks
- Page load time: < 2 seconds
- Message send latency: < 100ms
- Real-time update latency: < 50ms

## Monitoring & Troubleshooting

### Logging
- Log files: `logs/web_server.log`
- Log level: Configurable
- Client-side error logging

### Common Issues

1. **Page not loading**: Check server is running
2. **API errors**: Verify API Server connectivity
3. **Real-time updates not working**: Check A2A Server connectivity

## Security Considerations

### Authentication
- Session-based authentication
- Cookie-based sessions
- CSRF protection

### Authorization
- Role-based access control
- Admin-only features
- User data isolation

## Scaling

### Horizontal Scaling
- Multiple Web UI server instances
- Load balancing
- Shared session storage

### Vertical Scaling
- Optimize static file serving
- Increase connection limits
- Cache optimization

## Advanced Features

### Customization
- Custom themes
- Custom layouts
- Plugin system (if implemented)

### Integration
- Single Sign-On (SSO)
- External identity providers
- Custom authentication

## Best Practices

### UI Development
- Follow accessibility guidelines
- Test on multiple browsers
- Optimize for performance
- Implement error handling

### Development
- Use `server_control.sh` for server management
- Test with different screen sizes
- Monitor performance metrics

## Future Enhancements

- Enhanced mobile experience
- Dark mode
- Customizable UI themes
- Advanced analytics dashboard
- Plugin system

## Resources

- **Source Code**: `src/servers/web/`
- **Static Files**: `static/` (if applicable)
- **Templates**: `templates/` (if applicable)
- **Configuration**: `default.yaml`, `config.yaml`, `.env`
- **Related Documentation**:
  - [API_SERVER.md](API_SERVER.md) - API Server specification
  - [A2A_SERVER.md](A2A_SERVER.md) - A2A Server specification
  - [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture

## User Guide

### Getting Started

1. **Access the Web UI**: Navigate to `http://localhost:8080` in your browser
2. **Enter API Key**: On first access, you'll be prompted to enter your API key
3. **Select a Channel**: Choose a channel from the dropdown to start chatting
4. **Start Conversation**: Type your message and press Enter or click Send

### Chat Interface

The chat interface provides a conversational experience with expert agents:

- **Channel Selection**: Choose which expert channel to interact with
- **Session Management**: Automatically creates and manages conversation sessions
- **Message History**: View previous messages in the conversation
- **Real-time Responses**: Receive responses as they're generated

**Keyboard Shortcuts:**
- `Enter` - Send message
- `Shift+Enter` - New line in message
- `Ctrl+K` - Focus channel selector

### Channel Management

**Viewing Channels:**
1. Click "📡 Channels" in the navigation
2. View all available channels with their status
3. Click "Chat" button to start a conversation with a channel

**Creating Channels** (Admin only):
1. Navigate to Channels panel
2. Click "+ Create Channel"
3. Fill in channel details:
   - Name (unique identifier)
   - Expert configuration
   - Description
   - Context type
4. Save the channel

### Expert Configurations

**Viewing Experts:**
1. Click "🎓 Experts" in the navigation
2. View all expert configurations with their LLM provider and model
3. See which experts are enabled/disabled

**Creating Experts** (Admin only):
1. Navigate to Experts panel
2. Click "+ Create Expert"
3. Configure:
   - Name and title
   - LLM provider (Ollama, OpenAI, OpenRouter)
   - Model name
   - Temperature and max tokens
   - Prompt template
4. Save the expert

### Knowledge Base

**Searching Knowledge:**
1. Navigate to Knowledge panel
2. Use the search box to find relevant knowledge entries
3. Results show matching documents with metadata

**Adding Knowledge** (Admin only):
1. Navigate to Knowledge panel
2. Click "+ Add Knowledge"
3. Enter:
   - Content (text to index)
   - Metadata (title, source, etc.)
   - Collection name
4. Save to add to vector store

### Job Management

**Viewing Jobs:**
1. Navigate to Jobs panel
2. Filter by status (pending, processing, completed, failed)
3. View job details including:
   - Job type
   - Status
   - Creation time
   - Associated session/channel

**Job Actions:**
- **View**: Click "View" to see full job details
- **Resubmit**: Resubmit failed jobs (Admin only)
- **Stop**: Stop running jobs (Admin only)
- **Delete**: Remove job records (Admin only)

### User Management

**Viewing Users:**
1. Navigate to Users panel
2. See all users with their roles and status
3. View user details including email and display name

**Creating Users** (Admin only):
1. Navigate to Users panel
2. Click "+ Create User"
3. Enter:
   - Username (unique)
   - Email (unique)
   - Password (for local users)
   - Display name
   - Role (user, admin)
4. Save the user

### Group Management

**Viewing Groups:**
1. Navigate to Groups panel
2. See all groups with member counts
3. View group details and members

**Creating Groups** (Admin only):
1. Navigate to Groups panel
2. Click "+ Create Group"
3. Enter:
   - Group name (unique)
   - Description
   - Enabled status
4. Save the group

**Managing Group Members:**
1. Click "View" on a group
2. Add members by user ID
3. Update member roles (member, admin)
4. Remove members as needed

### File Management

**Viewing Files:**
1. Navigate to Files panel
2. See all uploaded multimedia files
3. Filter by file type (image, audio, video)

**Uploading Files:**
1. Click "+ Upload File"
2. Select file from your computer
3. File is automatically processed and stored

**Downloading Files:**
1. Click "Download" on any file
2. File downloads to your computer

### Prompt Generation

**Generating Prompts:**
1. Navigate to Prompts panel
2. Enter expert title and details
3. Click "Generate Prompt"
4. Review generated prompt and recommendations

**Test Case Generation:**
1. After generating a prompt, use the test case generator
2. Specify number of test cases
3. Review generated test cases for validation

### Expert Testing

**Running Test Suite:**
1. Navigate to Testing panel
2. Enter channel ID to test
3. Optionally provide custom test cases
4. Click "Run Test Suite"
5. Review test results including:
   - Pass/fail status
   - Response quality
   - Error messages

### Administration Dashboard

**System Status:**
- View overall system health
- Check server component status
- Monitor initialization progress

**Queue Status:**
- View job queue depth
- See pending/processing/completed counts
- Monitor Redis queue status (if enabled)

**Metrics:**
- View Prometheus metrics
- Monitor system performance
- Track usage statistics

---

## Admin Guide

### System Administration

**Accessing Admin Features:**
- Admin features require admin role
- Some features are restricted to admin users only
- Check user role in Users panel

**Key Admin Tasks:**

1. **User Management**
   - Create, update, delete users
   - Assign roles (user, admin)
   - Enable/disable user accounts
   - Reset passwords

2. **Group Management**
   - Create and manage groups
   - Assign group admins
   - Manage group membership
   - Configure group permissions

3. **Expert Configuration**
   - Create expert configurations
   - Configure LLM providers
   - Set up prompt templates
   - Enable/disable experts

4. **Channel Management**
   - Create channels
   - Link channels to experts
   - Configure channel settings
   - Manage channel access

5. **Knowledge Base Management**
   - Add knowledge entries
   - Manage collections
   - Update vector stores
   - Configure access controls

6. **Job Queue Management**
   - View all jobs
   - Resubmit failed jobs
   - Stop running jobs
   - Delete job records
   - Monitor queue status

7. **File Management**
   - View all uploaded files
   - Download files
   - Delete files
   - Monitor storage usage

8. **System Monitoring**
   - View system status
   - Monitor queue depth
   - Check server health
   - Review metrics

### Security Best Practices

1. **API Key Management**
   - Rotate API keys regularly
   - Use strong, unique API keys
   - Never commit API keys to version control
   - Store API keys securely

2. **User Access Control**
   - Assign minimum required roles
   - Regularly review user permissions
   - Disable unused accounts
   - Monitor user activity

3. **Group Permissions**
   - Use groups for access control
   - Assign group admins carefully
   - Review group membership regularly
   - Limit admin group membership

4. **Data Protection**
   - Enable audit logging
   - Review audit logs regularly
   - Implement data retention policies
   - Secure file storage

### Troubleshooting

#### Common Issues

**1. Web UI Not Loading**
- **Symptom**: Page doesn't load or shows error
- **Solution**:
  - Check Web UI server is running: `./server_control.sh status web`
  - Verify port 8080 is accessible
  - Check firewall settings
  - Review server logs: `logs/web_server.log`

**2. API Connection Errors**
- **Symptom**: "API unavailable" or connection errors
- **Solution**:
  - Verify API server is running: `./server_control.sh status api`
  - Check API server URL in configuration
  - Verify API key is correct
  - Check network connectivity
  - Review API server logs: `logs/api_server.log`

**3. Chat Not Responding**
- **Symptom**: Messages sent but no response
- **Solution**:
  - Check channel is enabled
  - Verify expert configuration is valid
  - Check LLM provider connectivity
  - Review job queue for errors
  - Check session status

**4. Authentication Failures**
- **Symptom**: "Unauthorized" errors
- **Solution**:
  - Verify API key is correct
  - Check API key hasn't expired
  - Verify user account is enabled
  - Check user role permissions

**5. File Upload Failures**
- **Symptom**: Files not uploading
- **Solution**:
  - Check file size limits
  - Verify file format is supported
  - Check storage directory permissions
  - Review storage space availability

**6. Knowledge Search Not Working**
- **Symptom**: No results from knowledge search
- **Solution**:
  - Verify vector store is configured
  - Check collection exists
  - Verify knowledge entries are indexed
  - Check vector store connectivity

**7. Job Queue Stuck**
- **Symptom**: Jobs not processing
- **Solution**:
  - Check queue manager status
  - Verify Redis connection (if enabled)
  - Review job errors
  - Restart queue processor if needed

**8. Test Suite Failures**
- **Symptom**: Expert tests failing
- **Solution**:
  - Verify channel configuration
  - Check LLM provider connectivity
  - Review test case requirements
  - Check expert configuration validity

### Performance Optimization

**1. Reduce Page Load Time**
- Enable static file caching
- Minimize JavaScript bundle size
- Use CDN for static assets
- Implement lazy loading

**2. Improve Chat Responsiveness**
- Use async job processing for long operations
- Implement WebSocket for real-time updates
- Cache frequently accessed data
- Optimize API calls

**3. Optimize Knowledge Search**
- Index knowledge efficiently
- Use appropriate vector store configuration
- Cache search results
- Limit result sets

### Monitoring

**Key Metrics to Monitor:**
- Page load times
- API response times
- Chat message latency
- Job queue depth
- Error rates
- User activity

**Log Files:**
- `logs/web_server.log` - Web UI server logs
- `logs/api_server.log` - API server logs
- `logs/app.log` - Application logs

**Health Checks:**
- `/health` - Server health status
- `/status` - System status
- `/metrics` - Prometheus metrics

---

## Support

- **Repository**: Expert Agent MCP Server
- **License**: Apache 2.0
- **Documentation**: See [README.md](../README.md) for more information

---

**Related Documentation:**
- [API_SERVER.md](API_SERVER.md) - API Server specification
- [MCP_SERVER.md](MCP_SERVER.md) - MCP Server specification
- [A2A_SERVER.md](A2A_SERVER.md) - A2A Server specification
- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) - Complete API reference
