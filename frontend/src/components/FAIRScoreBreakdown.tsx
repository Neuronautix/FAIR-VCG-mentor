import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline'
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked'
import {
  Box,
  Chip,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Paper,
  Typography,
} from '@mui/material'
import type { FAIRDimension, FAIRScore } from '../store/useStore'

const DIM_COLORS: Record<string, string> = {
  findable: '#7b1fa2',
  accessible: '#1565c0',
  interoperable: '#00695c',
  reusable: '#e65100',
}

const DIM_LABELS: Record<string, string> = {
  findable: 'F — Findable',
  accessible: 'A — Accessible',
  interoperable: 'I — Interoperable',
  reusable: 'R — Reusable',
}

function ScoreGauge({ score }: { score: number }) {
  const color =
    score >= 70 ? '#388e3c' : score >= 45 ? '#f57c00' : '#d32f2f'
  return (
    <Box sx={{ textAlign: 'center', py: 3 }}>
      <Box
        sx={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 120,
          height: 120,
          borderRadius: '50%',
          border: `8px solid ${color}`,
          background: `${color}15`,
        }}
      >
        <Box>
          <Typography variant="h3" fontWeight={800} color={color} lineHeight={1}>
            {score}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            / 100
          </Typography>
        </Box>
      </Box>
      <Typography variant="subtitle1" fontWeight={600} sx={{ mt: 1.5 }}>
        FAIR-Readiness Estimate
      </Typography>
      <Typography variant="caption" color="text.secondary">
        Rule-based score — not a regulatory certification
      </Typography>
    </Box>
  )
}

function DimensionCard({ dim, data }: { dim: string; data: FAIRDimension }) {
  const color = DIM_COLORS[dim]
  const pct = Math.round((data.score / data.max_score) * 100)
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
        <Typography variant="subtitle2" fontWeight={700} color={color}>
          {DIM_LABELS[dim]}
        </Typography>
        <Chip
          label={`${data.score} / ${data.max_score}`}
          size="small"
          sx={{ background: color, color: 'white', fontWeight: 700 }}
        />
      </Box>
      <LinearProgress
        variant="determinate"
        value={pct}
        sx={{
          mb: 1.5,
          height: 8,
          borderRadius: 4,
          background: `${color}20`,
          '& .MuiLinearProgress-bar': { background: color, borderRadius: 4 },
        }}
      />
      <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
        Main weakness: {data.main_weakness}
      </Typography>
      <List dense disablePadding>
        {Object.entries(data.criteria).map(([criterion, passed]) => (
          <ListItem key={criterion} disablePadding sx={{ py: 0.25 }}>
            <ListItemIcon sx={{ minWidth: 28 }}>
              {passed ? (
                <CheckCircleOutlineIcon fontSize="small" sx={{ color: '#388e3c' }} />
              ) : (
                <RadioButtonUncheckedIcon fontSize="small" sx={{ color: '#bdbdbd' }} />
              )}
            </ListItemIcon>
            <ListItemText
              primary={criterion}
              primaryTypographyProps={{ fontSize: 12, color: passed ? 'text.primary' : 'text.secondary' }}
            />
          </ListItem>
        ))}
      </List>
    </Paper>
  )
}

export default function FAIRScoreBreakdown({ score }: { score: FAIRScore }) {
  return (
    <Box>
      <ScoreGauge score={score.fair_score} />
      {(['findable', 'accessible', 'interoperable', 'reusable'] as const).map((dim) => (
        <DimensionCard key={dim} dim={dim} data={score[dim]} />
      ))}
    </Box>
  )
}
