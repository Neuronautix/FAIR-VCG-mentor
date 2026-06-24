import type { ReactNode } from 'react'
import ArticleIcon from '@mui/icons-material/Article'
import FindInPageIcon from '@mui/icons-material/FindInPage'
import AssessmentIcon from '@mui/icons-material/Assessment'
import BarChartIcon from '@mui/icons-material/BarChart'
import ChecklistIcon from '@mui/icons-material/Checklist'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import DownloadIcon from '@mui/icons-material/Download'
import InfoIcon from '@mui/icons-material/Info'
import ScienceIcon from '@mui/icons-material/Science'
import RuleIcon from '@mui/icons-material/Rule'
import TableChartIcon from '@mui/icons-material/TableChart'
import TuneIcon from '@mui/icons-material/Tune'
import {
  AppBar,
  Box,
  Chip,
  Container,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material'
import { useEffect } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { getLLMStatus } from '../api/client'
import { useStore } from '../store/useStore'

const DRAWER_WIDTH = 220

interface NavItem {
  label: string
  path: string
  icon: ReactNode
  alwaysEnabled?: boolean
  vcgResultsOnly?: boolean
  requiresTemplate?: boolean
}

const navItems: NavItem[] = [
  { label: 'Upload CSV', path: '/' },
  { label: 'NTS Analyser', path: '/nts-analyzer', alwaysEnabled: true },
  { label: 'Paper Import', path: '/paper-import', alwaysEnabled: true },
  { label: 'Overview', path: '/overview' },
  { label: 'Column Profile', path: '/columns' },
  { label: 'FAIR Score', path: '/fair-score' },
  { label: 'Metadata Wizard', path: '/metadata' },
  { label: 'Templates', path: '/templates', alwaysEnabled: true },
  { label: 'Template Fill', path: '/template-fill', requiresTemplate: true },
  { label: 'VCG Wizard', path: '/vcg' },
  { label: 'Export', path: '/export' },
  { label: 'VCG Results', path: '/vcg/results', vcgResultsOnly: true },
].map((item, i) => ({
  ...item,
  icon: [
    <CloudUploadIcon />, <FindInPageIcon />, <ArticleIcon />, <InfoIcon />, <TableChartIcon />,
    <AssessmentIcon />, <TuneIcon />, <RuleIcon />, <ChecklistIcon />, <ScienceIcon />,
    <DownloadIcon />, <BarChartIcon />,
  ][i],
}))

export default function Layout() {
  const location = useLocation()
  const navigate = useNavigate()
  const theme = useTheme()
  const { datasetId, importInfo, vcgStatus, llmEnabled, setLLMEnabled, llmStatus, setLLMStatus, templateId } =
    useStore()

  useEffect(() => {
    if (llmEnabled !== null) return
    getLLMStatus()
      .then((r) => {
        setLLMEnabled(r.enabled)
        setLLMStatus(r)
      })
      .catch(() => {
        setLLMEnabled(false)
        setLLMStatus({ enabled: false })
      })
  }, [llmEnabled, setLLMEnabled, setLLMStatus])

  // Derive a compact, provider-aware label for the LLM status chip.
  // A configured base_url means a local OpenAI-compatible endpoint (e.g. LM Studio) — surface "Local LLM"
  // so the fully-offline deployment story is visible in the UI.
  const isLocalLLM = Boolean(llmStatus?.base_url)
  const providerLabel = isLocalLLM
    ? 'Local LLM'
    : llmStatus?.provider === 'openai'
      ? 'OpenAI'
      : 'Claude'
  const model = llmStatus?.model ?? ''
  const shortModel = model.length > 20 ? `${model.slice(0, 19)}…` : model
  const llmChipLabel = `${providerLabel}${shortModel ? ` · ${shortModel}` : ''} · ${llmEnabled ? 'on' : 'off'}`

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar
        position="fixed"
        sx={{ zIndex: theme.zIndex.drawer + 1, background: 'linear-gradient(90deg, #1565c0 0%, #0288d1 100%)' }}
      >
        <Toolbar>
          <AssessmentIcon sx={{ mr: 1.5 }} />
          <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 700, letterSpacing: 0.5 }}>
            FAIR CSV Mentor
          </Typography>
          {importInfo && (
            <Chip
              label={importInfo.filename}
              size="small"
              sx={{ color: 'white', borderColor: 'rgba(255,255,255,0.6)', mr: 1 }}
              variant="outlined"
            />
          )}
          {llmEnabled !== null && (
            <Tooltip
              title={
                <Box sx={{ fontSize: 12, lineHeight: 1.6 }}>
                  <div>Provider: {llmStatus?.provider ?? 'anthropic'}</div>
                  <div>Model: {model || '—'}</div>
                  <div>Endpoint: {isLocalLLM ? llmStatus?.base_url : 'Anthropic API (cloud)'}</div>
                  <div>Status: {llmEnabled ? 'enabled' : 'disabled (no API key / endpoint)'}</div>
                  {isLocalLLM && <div>Running fully offline — no external API calls.</div>}
                </Box>
              }
            >
              <Chip
                label={llmChipLabel}
                size="small"
                sx={{
                  color: 'white',
                  borderColor: llmEnabled ? 'rgba(255,255,255,0.6)' : 'rgba(255,255,255,0.25)',
                  mr: 1,
                  fontSize: 11,
                }}
                variant="outlined"
              />
            </Tooltip>
          )}
          <Chip
            label="Assessment only — not regulatory certification"
            size="small"
            sx={{ color: 'rgba(255,255,255,0.7)', borderColor: 'rgba(255,255,255,0.3)', fontSize: 10 }}
            variant="outlined"
          />
        </Toolbar>
      </AppBar>

      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: DRAWER_WIDTH,
            boxSizing: 'border-box',
            borderRight: '1px solid rgba(0,0,0,0.08)',
            background: '#fafbfc',
          },
        }}
      >
        <Toolbar />
        <Box sx={{ overflow: 'auto', pt: 1 }}>
          <List dense>
            {navItems.map((item) => {
              const active = location.pathname === item.path
              const disabled =
                !item.alwaysEnabled &&
                item.path !== '/' &&
                (!datasetId ||
                  (item.vcgResultsOnly === true && vcgStatus !== 'done') ||
                  (item.requiresTemplate === true && !templateId))
              const tooltip =
                disabled && item.requiresTemplate && !templateId && datasetId
                  ? 'Assign a template first'
                  : ''
              const buttonNode = (
                <ListItemButton
                  selected={active}
                  disabled={disabled}
                  onClick={() => navigate(item.path)}
                  sx={{
                    mx: 1,
                    borderRadius: 2,
                    mb: 0.5,
                    '&.Mui-selected': {
                      background: 'rgba(25, 118, 210, 0.12)',
                      color: 'primary.main',
                      '& .MuiListItemIcon-root': { color: 'primary.main' },
                    },
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 36 }}>{item.icon}</ListItemIcon>
                  <ListItemText
                    primary={item.label}
                    primaryTypographyProps={{ fontSize: 13, fontWeight: active ? 600 : 400 }}
                  />
                </ListItemButton>
              )
              return (
                <ListItem key={item.path} disablePadding>
                  {tooltip ? (
                    <Tooltip title={tooltip} placement="right">
                      <span style={{ width: '100%' }}>{buttonNode}</span>
                    </Tooltip>
                  ) : (
                    buttonNode
                  )}
                </ListItem>
              )
            })}
          </List>
        </Box>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, overflowX: 'hidden', p: 3, pt: 0 }}>
        <Toolbar />
        <Container maxWidth="xl" sx={{ mt: 3, px: { xs: 0, sm: 2, md: 3 }, minWidth: 0 }}>
          <Outlet />
        </Container>
      </Box>
    </Box>
  )
}
