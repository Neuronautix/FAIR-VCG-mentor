import { Alert, Box, LinearProgress, Typography } from '@mui/material'

interface Props {
  status: 'not_started' | 'running' | 'done' | 'failed' | null
  activeStep?: string
  errorMessage?: string
}

export default function AgentStatusBar({ status, activeStep, errorMessage }: Props) {
  if (!status || status === 'not_started') return null

  if (status === 'running') {
    return (
      <Box sx={{ mt: 2 }}>
        <LinearProgress variant="indeterminate" />
        {activeStep && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
            {activeStep}
          </Typography>
        )}
      </Box>
    )
  }

  if (status === 'done') {
    return (
      <Box sx={{ mt: 2 }}>
        <Alert severity="success">VCG generation complete.</Alert>
      </Box>
    )
  }

  if (status === 'failed') {
    return (
      <Box sx={{ mt: 2 }}>
        <Alert severity="error">{errorMessage ?? 'VCG generation failed. Please try again.'}</Alert>
      </Box>
    )
  }

  return null
}
