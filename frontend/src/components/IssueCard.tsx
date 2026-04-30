import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import { Box, Chip, Collapse, Paper, Typography } from '@mui/material'
import { useState } from 'react'
import type { Issue } from '../store/useStore'

const SEVERITY_CONFIG = {
  high: { icon: <ErrorOutlineIcon fontSize="small" />, color: '#d32f2f', bg: '#fff5f5', border: '#ffcdd2' },
  medium: { icon: <WarningAmberIcon fontSize="small" />, color: '#e65100', bg: '#fff8f0', border: '#ffe0b2' },
  low: { icon: <InfoOutlinedIcon fontSize="small" />, color: '#0288d1', bg: '#f0f8ff', border: '#b3e5fc' },
}

export default function IssueCard({ issue }: { issue: Issue }) {
  const [open, setOpen] = useState(false)
  const cfg = SEVERITY_CONFIG[issue.severity] ?? SEVERITY_CONFIG.low

  return (
    <Paper
      variant="outlined"
      sx={{
        mb: 1.5,
        border: `1px solid ${cfg.border}`,
        background: cfg.bg,
        cursor: 'pointer',
        transition: 'box-shadow 0.15s',
        '&:hover': { boxShadow: '0 2px 8px rgba(0,0,0,0.10)' },
      }}
      onClick={() => setOpen((v) => !v)}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 1.5 }}>
        <Box sx={{ color: cfg.color, display: 'flex', alignItems: 'center' }}>{cfg.icon}</Box>
        <Box sx={{ flex: 1 }}>
          <Typography variant="body2" fontWeight={600} color={cfg.color}>
            {issue.problem}
          </Typography>
          {issue.column && (
            <Chip label={issue.column} size="small" sx={{ mt: 0.5, height: 18, fontSize: 11 }} />
          )}
        </Box>
        <Chip
          label={issue.severity}
          size="small"
          sx={{
            background: cfg.color,
            color: 'white',
            fontWeight: 600,
            fontSize: 11,
            height: 20,
          }}
        />
      </Box>

      <Collapse in={open}>
        <Box sx={{ px: 2, pb: 2, pt: 0.5, borderTop: `1px solid ${cfg.border}` }}>
          <Box sx={{ mb: 1 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={700} sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Why it matters
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
              {issue.why_it_matters}
            </Typography>
          </Box>
          <Box
            sx={{ background: 'rgba(0,0,0,0.04)', borderRadius: 1, p: 1.25 }}
          >
            <Typography variant="caption" color="text.secondary" fontWeight={700} sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Suggested fix
            </Typography>
            <Typography variant="body2" sx={{ mt: 0.25 }}>
              {issue.suggested_fix}
            </Typography>
          </Box>
        </Box>
      </Collapse>
    </Paper>
  )
}
