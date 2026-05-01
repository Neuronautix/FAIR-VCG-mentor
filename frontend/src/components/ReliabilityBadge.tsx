import { Box, Chip, Typography } from '@mui/material'

interface Props {
  score: number  // 0-1
}

export default function ReliabilityBadge({ score }: Props) {
  const pct = (score * 100).toFixed(0) + '%'

  let color: 'success' | 'warning' | 'error'
  let label: string
  let interpretation: string

  if (score >= 0.7) {
    color = 'success'
    label = 'High reliability'
    interpretation =
      'The virtual control group closely matches the real population across all key covariates and outcomes.'
  } else if (score >= 0.5) {
    color = 'warning'
    label = 'Moderate'
    interpretation =
      'The virtual control group is a reasonable approximation. Check covariate balance before drawing conclusions.'
  } else {
    color = 'error'
    label = 'Low reliability — review recommended'
    interpretation =
      'Significant imbalances detected. Results should be interpreted with caution; consider adding more covariates or using a different method.'
  }

  return (
    <Box>
      <Chip label={`${pct} — ${label}`} color={color} variant="outlined" />
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        {interpretation}
      </Typography>
    </Box>
  )
}
