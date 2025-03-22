# Agent System Design: Separation of Responsibilities

## Message Routing Architecture

In our multi-agent system, we follow a clear separation of responsibilities for message routing to ensure maintainability, flexibility, and proper encapsulation of functionality.

### Core Principle: Message Broker Determines Routing

**The most important principle: Agents should NEVER set receiver_id themselves.**

Instead, the system follows these key principles:

1. **Message Broker Role**: The MessageBrokerAgent is solely responsible for determining where messages should be routed. It analyzes message content using LLM reasoning and decides which agent should receive a message next.

2. **AgentServer Role**: The AgentServer is responsible for creating new messages with the appropriate receiver_id after consulting the broker. It's the only component that should actually set the receiver_id field on messages.

3. **Agent Role**: Agents process messages and generate responses but do not specify the next receiver. They focus on their specialized task and leave routing decisions to the broker.

## Implementation Guidelines

### For Agent Developers

When implementing an agent's `process_message` method:

```python
async def process_message(self, message: Message) -> Optional[Message]:
    # Process the message and generate a response
    response = Message(
        sender_id=self.agent_id,
        # DON'T set receiver_id here - let the broker decide
        content={"text": "My response"},
        message_type="text"
    )
    return response
```

### For Message Broker

The broker only determines the next agent:

```python
async def route_message_chain(self, original_message, response_message) -> str:
    # Analyze messages and determine the most appropriate next agent
    next_agent_id = await self._determine_next_agent(
        original_message, response_message
    )
    # Return only the ID - don't modify messages directly
    return next_agent_id
```

### For Agent Server

The server handles setting the receiver_id based on broker's decision:

```python
async def route_message(self, message):
    if not message.receiver_id:
        next_agent_id = await self.message_broker.route_message_chain(
            original_message, message
        )
        
        # Create a new message with the proper receiver_id
        routed_message = Message(
            **message.dict(),
            receiver_id=next_agent_id
        )
        
        # Send the routed message to the target agent
        await self.agents[next_agent_id].add_message(routed_message)
    else:
        # Handle direct routing if receiver_id already specified
        ...
```

## Benefits of This Approach

1. **Clear Separation of Concerns**: Each component focuses on its specific responsibility.
2. **Centralized Routing Logic**: All routing decisions are made in one place, making the system easier to understand and maintain.
3. **Flexible Routing**: The broker can implement complex routing strategies without needing to modify agent implementations.
4. **Easier Testing**: Components can be tested in isolation with clear boundaries of responsibility.
5. **Enhanced Monitoring**: Routing decisions are explicit and can be logged/monitored effectively.

## Common Pitfalls to Avoid

1. ❌ **DON'T** have agents set receiver_id directly in their response messages
2. ❌ **DON'T** bypass the broker for routing decisions (except for explicitly directed messages)
3. ❌ **DON'T** modify message objects in-place; create new messages with the updated routing information

Following these guidelines ensures a clean, maintainable architecture for our multi-agent system. 