import type { ReactNode } from 'react'
import GitHubIcon from '@mui/icons-material/GitHub'
import AssessmentIcon from '@mui/icons-material/Assessment'
import ChecklistIcon from '@mui/icons-material/Checklist'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import DownloadIcon from '@mui/icons-material/Download'
import InfoIcon from '@mui/icons-material/Info'
import RuleIcon from '@mui/icons-material/Rule'
import SettingsIcon from '@mui/icons-material/Settings'
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
import { useStore } from '../store/useStore'

const DRAWER_WIDTH = 220

interface NavItem {
  label: string
  path: string
  icon: ReactNode
  alwaysEnabled?: boolean
  requiresTemplate?: boolean
}

const navItems: NavItem[] = [
  { label: 'Import', path: '/', alwaysEnabled: true },
  { label: 'Templates', path: '/templates', alwaysEnabled: true },
  { label: 'FAIR Score', path: '/fair-score' },
  { label: 'Metadata Wizard', path: '/metadata' },
  { label: 'Template Fill', path: '/template-fill', requiresTemplate: true },
  { label: 'CSV Overview', path: '/overview' },
  { label: 'Column Profile', path: '/columns' },
  { label: 'Export', path: '/export' },
  { label: 'Settings', path: '/settings', alwaysEnabled: true },
].map((item, i) => ({
  ...item,
  icon: [
    <CloudUploadIcon />, <RuleIcon />, <AssessmentIcon />, <TuneIcon />,
    <ChecklistIcon />, <InfoIcon />, <TableChartIcon />, <DownloadIcon />, <SettingsIcon />,
  ][i],
}))

export default function Layout() {
  const location = useLocation()
  const navigate = useNavigate()
  const theme = useTheme()
  const { datasetId, importInfo, aiConfigured, setAIConfigured, templateId, assessmentOnly } = useStore()

  useEffect(() => {
    if (aiConfigured !== null) return
    fetch('/api/llm/status')
      .then((r) => r.json())
      .then((data) => setAIConfigured(data.enabled ?? false))
      .catch(() => setAIConfigured(false))
  }, [aiConfigured, setAIConfigured])

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
          {aiConfigured !== null && (
            <Chip
              label={aiConfigured ? 'AI suggestions: on' : 'AI suggestions: off'}
              size="small"
              sx={{
                color: 'white',
                borderColor: aiConfigured ? 'rgba(255,255,255,0.6)' : 'rgba(255,255,255,0.25)',
                mr: 1,
                fontSize: 11,
              }}
              variant="outlined"
            />
          )}
          {assessmentOnly && (
            <Chip
              label="ARRIVE/PREPARE mode (no dataset)"
              size="small"
              sx={{ color: 'rgba(255,255,255,0.85)', borderColor: 'rgba(255,255,255,0.5)', mr: 1, fontSize: 10 }}
              variant="outlined"
            />
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

      <Box component="main" sx={{ flexGrow: 1, p: 3, pt: 0, display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <Toolbar />
        <Container maxWidth="xl" sx={{ mt: 3, flexGrow: 1 }}>
          <Outlet />
        </Container>
        <Box
          component="footer"
          sx={{
            mt: 6,
            py: 2,
            borderTop: '1px solid',
            borderColor: 'divider',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 1.5,
            flexWrap: 'wrap',
          }}
        >
          <Box
            component="a"
            href="https://www.neuronautix.com"
            target="_blank"
            rel="noopener noreferrer"
            sx={{ display: 'flex', alignItems: 'center' }}
          >
            <Box
              component="img"
              src="/neuronautix_logo.png"
              alt="Neuronautix"
              sx={{ height: 28 }}
            />
          </Box>
          <Typography variant="caption" color="text.secondary">
            Made with{' '}
            <Box component="span" sx={{ color: '#e53935' }}>♥</Box>
            {' '}by{' '}
            <Box
              component="a"
              href="https://www.neuronautix.com"
              target="_blank"
              rel="noopener noreferrer"
              sx={{ fontWeight: 600, color: 'text.primary', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
            >
              Neuronautix
            </Box>
            {' '}·{' '}
            <Box
              component="a"
              href="https://dhuzard.github.io"
              target="_blank"
              rel="noopener noreferrer"
              sx={{ color: 'text.secondary', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
            >
              Damien Huzard
            </Box>
          </Typography>
          <Box
            component="a"
            href="https://github.com/Neuronautix/"
            target="_blank"
            rel="noopener noreferrer"
            sx={{ display: 'flex', alignItems: 'center', color: 'text.secondary', '&:hover': { color: 'text.primary' } }}
          >
            <GitHubIcon sx={{ fontSize: 18 }} />
          </Box>
        </Box>
      </Box>
    </Box>
  )
}
