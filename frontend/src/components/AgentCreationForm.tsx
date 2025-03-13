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

export const AgentCreationForm: React.FC = () => {
  const { addAgent } = useAgentStore();
  const [loading, setLoading] = useState(false);
  const [options, setOptions] = useState<AgentOptions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
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
        console.log('Fetching agent options from: http://localhost:8000/api/agent-options');
        const response = await fetch('http://localhost:8000/api/agent-options');
        console.log('Response status:', response.status);
        if (!response.ok) {
          throw new Error(`Failed to fetch agent options: ${response.status} ${response.statusText}`);
        }
        const data = await response.json();
        console.log('Received agent options:', data);
        setOptions(data);
      } catch (err) {
        console.error('Error fetching agent options:', err);
        setError(err instanceof Error ? err.message : 'An unknown error occurred');
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
      setError('Please fill in all required fields');
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
      setSuccess(`Agent ${name} created successfully!`);
      
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
        status: 'active',
        capabilities: selectedCapabilities,
      });
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
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
  
  return (
    <Paper elevation={3} sx={{ p: 3, mb: 3 }}>
      <Typography variant="h5" gutterBottom>
        Create New Agent
      </Typography>
      
      <Box component="form" onSubmit={handleSubmit} sx={{ mt: 2 }}>
        <TextField
          fullWidth
          label="Agent Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          margin="normal"
          required
        />
        
        <FormControl fullWidth margin="normal" required>
          <InputLabel>Agent Type</InputLabel>
          <Select
            value={agentType}
            onChange={(e) => setAgentType(e.target.value)}
            label="Agent Type"
          >
            {options?.agent_types.map((type) => (
              <MenuItem key={type.id} value={type.id}>
                <Box>
                  <Typography variant="body1">{type.name}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {type.description}
                  </Typography>
                </Box>
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        
        <FormControl fullWidth margin="normal" required>
          <InputLabel>Provider</InputLabel>
          <Select
            value={provider}
            onChange={handleProviderChange}
            label="Provider"
          >
            {options?.providers.map((p) => (
              <MenuItem key={p.id} value={p.id}>
                {p.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        
        <FormControl fullWidth margin="normal" required disabled={!provider}>
          <InputLabel>Model</InputLabel>
          <Select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            label="Model"
          >
            {provider && options?.models[provider]?.map((m) => (
              <MenuItem key={m} value={m}>
                {m}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        
        <FormControl fullWidth margin="normal" required>
          <InputLabel>Capabilities</InputLabel>
          <Select
            multiple
            value={selectedCapabilities}
            onChange={handleCapabilityChange}
            input={<OutlinedInput label="Capabilities" />}
            renderValue={(selected) => (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                {selected.map((value) => {
                  const capability = options?.capabilities.find(c => c.id === value);
                  return (
                    <Chip key={value} label={capability?.name || value} />
                  );
                })}
              </Box>
            )}
          >
            {options?.capabilities.map((capability) => (
              <MenuItem key={capability.id} value={capability.id}>
                <Box>
                  <Typography variant="body1">{capability.name}</Typography>
                  <Typography variant="caption" color="text.secondary">
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
          sx={{ mt: 3 }}
          disabled={loading}
        >
          {loading ? <CircularProgress size={24} /> : 'Create Agent'}
        </Button>
      </Box>
      
      <Snackbar 
        open={!!error} 
        autoHideDuration={6000} 
        onClose={() => setError(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={() => setError(null)} severity="error">
          {error}
        </Alert>
      </Snackbar>
      
      <Snackbar 
        open={!!success} 
        autoHideDuration={6000} 
        onClose={() => setSuccess(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={() => setSuccess(null)} severity="success">
          {success}
        </Alert>
      </Snackbar>
    </Paper>
  );
}; 