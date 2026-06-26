---
template-id: T-A2A
template-version: 1.0
applies-to: docs/A2A-REFERENCE.md
registry: service
required: must-have
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

# expert-agent-mcp-server — A2A-REFERENCE

> **Template version:** T-A2A v1.0 — Agent-to-Agent endpoint surface.

## 1. Auth model
A2A auth (`api_key` typically); service-key vs role-key forwarding; RBAC enforcement point.

## 2. Endpoints

| Method | Path | Auth | RBAC | Summary |
|---|---|---|---|---|

## 3. Message envelope
A2A request/response shape; correlation IDs; streaming behaviour.

## 4. Tools (re-exposed)
List of tools available via A2A and their MCP-equivalent.

## 5. Examples
**You MUST include:** at least one worked A2A call from an upstream service.

## 6. Cross-references
- [API-REFERENCE.md](API-REFERENCE.md)
- [MCP-REFERENCE.md](MCP-REFERENCE.md)
- PS-72-mcp-a2a-webui.md
- PS-72b-agent-to-agent.md

## 7. Project-specific notes



<!-- W28C-1710a recovery: full content from archive/2026-06-12/A2A_SERVER.md (archived sha256=0356c76b60d7, 381 lines) -->

## Recovered domain content — `archive/2026-06-12/A2A_SERVER.md` (381 lines)

_This section carries forward the full content of the archived predecessor doc verbatim. Topic checklist + SHA256 chain in `cloud-dog-ai-platform-standards/working/evidence/W28C-1710a/per-doc/expert-agent-mcp-server/A2A_SERVER.md.topics.tsv`. Archive contents are unchanged (sha256 stable)._

# A2A Server Documentation
**Version:** 0.1 • 2025-01-XX

## Overview

The A2A (Agent-to-Agent) Server provides real-time streaming for events and status updates. It enables bidirectional communication between agents using WebSocket-based protocols.

**Port:** 8082 (configurable via `CLOUD_DOG__EXPERT__A2A_SERVER__PORT`)

## Quick Start

### Running the A2A Server

```bash
# Using server control script (recommended)
./server_control.sh start a2a

# Or manually (development only)
python3 start_a2a_server.py
```

### Configuration

A2A Server configuration is loaded from:
1. Environment Variables (`CLOUD_DOG__EXPERT__*`)
2. `.env` file
3. `config.yaml`
4. `default.yaml`

**Key Configuration Options:**
```bash
CLOUD_DOG__EXPERT__A2A_SERVER__PORT=8082
CLOUD_DOG__EXPERT__A2A_SERVER__HOST=0.0.0.0
```

## Key Features

### 1. Real-Time Streaming
- WebSocket-based bidirectional communication
- Event streaming for session updates
- Status updates in real-time

### 2. WebSocket Topics
- Session events
- Message events
- Status updates
- System notifications

### 3. Natural Language Commands
- Natural language command processing
- Agent-to-agent communication
- Event-driven architecture

## Architecture

### Components

- **WebSocket Server**: WebSocket protocol handler
- **Event Manager**: Event distribution
- **Topic Manager**: Topic-based messaging
- **API Client**: Communication with API Server

### Data Flow

```
Agent Client
  ↓
A2A Server (WebSocket)
  ↓
Topic Subscription
  ↓
Event Distribution
  ↓
Agent Client
```

## Protocol/Interface Details

### WebSocket Protocol

#### Connection
```javascript
const ws = new WebSocket('ws://localhost:8082');
```

#### Authentication
```json
{
  "type": "auth",
  "api_key": "your-api-key"
}
```

### WebSocket Topics

#### 1. Session Events
Topic: `sessions.{session_id}`

**Events:**
- `session.created`
- `session.updated`
- `session.ended`
- `session.message.added`

**Example:**
```json
{
  "topic": "sessions.session-uuid",
  "event": "session.message.added",
  "data": {
    "session_id": "session-uuid",
    "message": {
      "role": "user",
      "content": "User message"
    }
  }
}
```

#### 2. User Events
Topic: `users.{user_id}`

**Events:**
- `user.sessions.updated`
- `user.preferences.updated`

#### 3. System Events
Topic: `system`

**Events:**
- `system.status`
- `system.health`
- `system.llm.status`

### Natural Language Commands

#### Command Format
```json
{
  "type": "command",
  "command": "natural language command",
  "context": {
    "session_id": "session-uuid"
  }
}
```

#### Example Commands
- "Start a new session with the default expert"
- "Get status of session {session_id}"
- "List my active sessions"

## Key Flows

### Event Streaming Flow
```
Client connects
  ↓
Authenticate
  ↓
Subscribe to topics
  ↓
Receive events
  ↓
Process events
```

### Command Processing Flow
```
Client sends command
  ↓
Parse natural language
  ↓
Execute via API Server
  ↓
Return result
  ↓
Publish event
```

## Usage Examples

### WebSocket Connection
```javascript
const ws = new WebSocket('ws://localhost:8082');

ws.onopen = () => {
  // Authenticate
  ws.send(JSON.stringify({
    type: 'auth',
    api_key: 'your-api-key'
  }));
  
  // Subscribe to session events
  ws.send(JSON.stringify({
    type: 'subscribe',
    topic: 'sessions.session-uuid'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data);
};
```

### Python Client Example
```python
import asyncio
import websockets
import json

async def connect():
    uri = "ws://localhost:8082"
    async with websockets.connect(uri) as websocket:
        # Authenticate
        await websocket.send(json.dumps({
            "type": "auth",
            "api_key": "your-api-key"
        }))
        
        # Subscribe
        await websocket.send(json.dumps({
            "type": "subscribe",
            "topic": "sessions.session-uuid"
        }))
        
        # Listen for events
        async for message in websocket:
            event = json.loads(message)
            print(f"Event: {event}")
```

## Configuration

### Environment Variables

```bash
CLOUD_DOG__EXPERT__A2A_SERVER__PORT=8082
CLOUD_DOG__EXPERT__A2A_SERVER__HOST=0.0.0.0
CLOUD_DOG__EXPERT__API_SERVER__URL=http://localhost:8083
```

See [PARAMETERS.md](PARAMETERS.md) for complete configuration reference.

## Startup & Deployment

### Development
```bash
./server_control.sh start a2a
```

### Production
- Use `server_control.sh` for service management
- Ensure API Server is accessible
- Configure WebSocket timeouts
- Set up load balancing if needed

## Error Handling

### Error Response Format
```json
{
  "type": "error",
  "error": "Error message description",
  "code": "ERROR_CODE"
}
```

### Common Errors
- Authentication failed
- Invalid topic
- Connection timeout
- API Server unavailable

## Performance

### Optimization
- Connection pooling
- Event batching
- Topic-based filtering
- Efficient message serialization

### Benchmarks
- Connection establishment: < 100ms
- Event latency: < 50ms
- Concurrent connections: Configurable

## Monitoring & Troubleshooting

### Logging
- Log files: `logs/a2a_server.log`
- Log level: Configurable

### Metrics
- Active connections
- Events per second
- Error rate

### Common Issues

1. **Connection timeout**: Check network connectivity
2. **Authentication failed**: Verify API key
3. **Events not received**: Check topic subscription

## Security Considerations

### Authentication
- API key authentication required
- WebSocket connection authentication
- Session-based access control

### Authorization
- Topic-based access control
- User-based event filtering

## Scaling

### Horizontal Scaling
- Multiple A2A server instances
- Load balancing for WebSocket connections
- Shared event bus (if implemented)

### Vertical Scaling
- Increase connection limits
- Optimize event processing
- Adjust WebSocket buffer sizes

## Advanced Features

### Event Filtering
- Topic-based filtering
- Event type filtering
- Custom filter expressions

### Command Processing
- Natural language understanding
- Command chaining
- Context-aware commands

## Best Practices

### WebSocket Usage
- Implement reconnection logic
- Handle connection errors gracefully
- Use appropriate timeouts
- Subscribe only to needed topics

### Development
- Use `server_control.sh` for server management
- Test with multiple concurrent connections
- Monitor event latency

## Future Enhancements

- GraphQL subscriptions
- Enhanced natural language processing
- Event replay capability
- Multi-protocol support

## Resources

- **Source Code**: `src/servers/a2a/`
- **Configuration**: `default.yaml`, `config.yaml`, `.env`
- **Related Documentation**:
  - [API_SERVER.md](API_SERVER.md) - API Server specification
  - [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
  - [PARAMETERS.md](PARAMETERS.md) - Configuration parameters

## Support

- **Repository**: Expert Agent MCP Server
- **License**: Apache 2.0

---

**Related Documentation:**
- [API_SERVER.md](API_SERVER.md) - API Server specification
- [MCP_SERVER.md](MCP_SERVER.md) - MCP Server specification
- [WEB_UI.md](WEB_UI.md) - Web UI Server specification
