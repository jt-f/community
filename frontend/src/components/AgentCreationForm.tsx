import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  OutlinedInput,
  Typography,
  Paper,
  CircularProgress,
  Snackbar,
  Alert,
  SelectChangeEvent,
} from '@mui/material';
import { Add as AddIcon } from '@mui/icons-material';
import { useAgentStore } from '../store/agentStore';

interface AgentOption {
  id: string;
  name: string;
  description: string;
}

interface AgentOptions {
  agent_types: AgentOption[];
  providers: AgentOption[];
  models: Record<string, string[]>;
  capabilities: AgentOption[];
}

// Error boundary component to catch rendering errors
class ErrorBoundaryWrapper extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: any) {
    return { hasError: true };
  }

  componentDidCatch(error: any, errorInfo: any) {
    console.error("Error caught by boundary:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Box p={3}>
          <Typography color="error">
            Something went wrong. Please try again later.
          </Typography>
        </Box>
      );
    }

    return this.props.children;
  }
}

export const AgentCreationForm: React.FC<{ onAgentCreated?: () => void }> = ({ onAgentCreated }) => {
  const { addAgent } = useAgentStore();
  const [loading, setLoading] = useState(false);
  const [options, setOptions] = useState<AgentOptions | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  // Form state
  const [name, setName] = useState('');
  const [agentType, setAgentType] = useState('');
  const [provider, setProvider] = useState('');
  const [model, setModel] = useState('');
  const [selectedCapabilities, setSelectedCapabilities] = useState<string[]>([]);
  
  // Fetch available options from the backend
  useEffect(() => {
    const fetchOptions = async () => {
      try {
        setLoading(true);
        // Use a direct URL for testing
        const response = await fetch('http://localhost:8000/api/agent-options');
        if (!response.ok) {
          throw new Error(`Failed to fetch agent options: ${response.status} ${response.statusText}`);
        }
        const data = await response.json();
        setOptions(data);
      } catch (err) {
        console.error('Error fetching agent options:', err);
        const message = err instanceof Error ? err.message : 'An unknown error occurred';
        setErrorMessage(message);
      } finally {
        setLoading(false);
      }
    };
    
    fetchOptions();
  }, []);
  
  // Handle provider change to reset model selection
  const handleProviderChange = (event: SelectChangeEvent) => {
    setProvider(event.target.value);
    setModel(''); // Reset model when provider changes
  };
  
  // Handle capability selection
  const handleCapabilityChange = (event: SelectChangeEvent<string[]>) => {
    const value = event.target.value;
    setSelectedCapabilities(typeof value === 'string' ? value.split(',') : value);
  };
  
  // Handle form submission
  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    
    if (!name || !agentType || !provider || !model || selectedCapabilities.length === 0) {
      setErrorMessage('Please fill in all required fields');
      return;
    }
    
    try {
      setLoading(true);
      
      const agentConfig = {
        name,
        agent_type: agentType,
        model,
        provider,
        capabilities: selectedCapabilities,
        parameters: {
          temperature: 0.7,
        }
      };
      
      // Use a direct URL for testing
      console.log('Submitting agent to: http://localhost:8000/api/agents');
      const response = await fetch('http://localhost:8000/api/agents', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(agentConfig),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create agent');
      }
      
      const result = await response.json();
      setSuccessMessage(`Agent ${name} created successfully!`);
      
      // Reset form
      setName('');
      setAgentType('');
      setProvider('');
      setModel('');
      setSelectedCapabilities([]);
      
      // Refresh agents in the store
      addAgent({
        id: result.agent_id,
        name,
        type: agentType,
        status: 'idle',
        capabilities: selectedCapabilities,
        model,
        provider
      });
      
      // Call the onAgentCreated callback if provided
      if (onAgentCreated) {
        onAgentCreated();
      }
      
    } catch (err) {
      console.error('Error creating agent:', err);
      const message = err instanceof Error ? err.message : 'An unknown error occurred';
      setErrorMessage(message);
    } finally {
      setLoading(false);
    }
  };
  
  if (loading && !options) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" p={3}>
        <CircularProgress />
      </Box>
    );
  }
  
  // Ensure we have valid data to render
  const safeOptions = options || {
    agent_types: [],
    providers: [],
    models: {},
    capabilities: []
  };
  
  return (
    <ErrorBoundaryWrapper>
      <Paper 
        elevation={3} 
        sx={{ 
          p: 3, 
          mb: 3, 
          maxHeight: '80vh', 
          overflow: 'auto',
          '&::-webkit-scrollbar': {
            width: '8px',
          },
          '&::-webkit-scrollbar-thumb': {
            backgroundColor: 'rgba(0, 255, 65, 0.2)',
            borderRadius: '4px',
          },
          '&::-webkit-scrollbar-track': {
            backgroundColor: 'rgba(0, 0, 0, 0.1)',
          }
        }}
      >
        <Typography variant="h5" gutterBottom>
          Create New Agent
        </Typography>
        
        <Box component="form" onSubmit={handleSubmit} sx={{ mt: 2 }}>
          <TextField
            fullWidth
            label="Agent Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            margin="dense"
            required
            size="small"
          />
          
          <FormControl fullWidth margin="dense" required size="small">
            <InputLabel>Agent Type</InputLabel>
            <Select
              value={agentType}
              onChange={(e) => setAgentType(e.target.value)}
              label="Agent Type"
            >
              {safeOptions.agent_types.map((type) => (
                <MenuItem key={type.id} value={type.id}>
                  <Box>
                    <Typography variant="body2">{type.name}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                      {type.description}
                    </Typography>
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          
          <FormControl fullWidth margin="dense" required size="small">
            <InputLabel>Provider</InputLabel>
            <Select
              value={provider}
              onChange={handleProviderChange}
              label="Provider"
            >
              {safeOptions.providers.map((p) => (
                <MenuItem key={p.id} value={p.id}>
                  {p.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          
          <FormControl fullWidth margin="dense" required disabled={!provider} size="small">
            <InputLabel>Model</InputLabel>
            <Select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              label="Model"
            >
              {provider && safeOptions.models[provider]?.map((m) => (
                <MenuItem key={m} value={m}>
                  {m}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          
          <FormControl fullWidth margin="dense" required size="small">
            <InputLabel>Capabilities</InputLabel>
            <Select
              multiple
              value={selectedCapabilities}
              onChange={handleCapabilityChange}
              input={<OutlinedInput label="Capabilities" />}
              renderValue={(selected) => (
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {selected.map((value) => {
                    const capability = safeOptions.capabilities.find(c => c.id === value);
                    return (
                      <Chip key={value} label={capability?.name || value} size="small" />
                    );
                  })}
                </Box>
              )}
              MenuProps={{
                PaperProps: {
                  style: {
                    maxHeight: 224,
                  },
                },
              }}
            >
              {safeOptions.capabilities.map((capability) => (
                <MenuItem key={capability.id} value={capability.id}>
                  <Box>
                    <Typography variant="body2">{capability.name}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                      {capability.description}
                    </Typography>
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          
          <Button
            type="submit"
            variant="contained"
            color="primary"
            startIcon={<AddIcon />}
            sx={{ mt: 2 }}
            disabled={loading}
            size="medium"
          >
            {loading ? <CircularProgress size={24} /> : 'Create Agent'}
          </Button>
        </Box>
        
        <Snackbar 
          open={!!errorMessage} 
          autoHideDuration={6000} 
          onClose={() => setErrorMessage(null)}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          <Alert onClose={() => setErrorMessage(null)} severity="error">
            {errorMessage}
          </Alert>
        </Snackbar>
        
        <Snackbar 
          open={!!successMessage} 
          autoHideDuration={6000} 
          onClose={() => setSuccessMessage(null)}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          <Alert onClose={() => setSuccessMessage(null)} severity="success">
            {successMessage}
          </Alert>
        </Snackbar>
      </Paper>
    </ErrorBoundaryWrapper>
  );
}; 