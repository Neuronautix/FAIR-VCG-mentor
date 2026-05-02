import type { ReactNode } from 'react'
import AssessmentIcon from '@mui/icons-material/Assessment'
import BarChartIcon from '@mui/icons-material/BarChart'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import DownloadIcon from '@mui/icons-material/Download'
import InfoIcon from '@mui/icons-material/Info'
import ScienceIcon from '@mui/icons-material/Science'
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
  Typography,
  useTheme,
} from '@mui/material'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useStore } from '../store/useStore'

const DRAWER_WIDTH = 220

interface NavItem {
  label: string
  path: string
  icon: ReactNode
  vcgResultsOnly?: boolean
}

const navItems: NavItem[] = [
  { label: 'Upload CSV', path: '/' },
  { label: 'Overview', path: '/overview' },
  { label: 'Column Profile', path: '/columns' },
  { label: 'FAIR Score', path: '/fair-score' },
  { label: 'Metadata Wizard', path: '/metadata' },
  { label: 'Export', path: '/export' },
  { label: 'VCG Wizard', path: '/vcg' },
  { label: 'VCG Results', path: '/vcg/results', vcgResultsOnly: true },
].map((item, i) => ({
  ...item,
  icon: [
    <CloudUploadIcon />, <InfoIcon />, <TableChartIcon />, <AssessmentIcon />,
    <TuneIcon />, <DownloadIcon />, <ScienceIcon />, <BarChartIcon />,
  ][i],
}))

export default function Layout() {
  const location = useLocation()
  const navigate = useNavigate()
  const theme = useTheme()
  const { datasetId, importInfo, vcgStatus } = useStore()

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
              const disabled = item.path !== '/' && (!datasetId || (item.vcgResultsOnly === true && vcgStatus !== 'done'))
              return (
                <ListItem key={item.path} disablePadding>
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
                </ListItem>
              )
            })}
          </List>
        </Box>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, p: 3, pt: 0 }}>
        <Toolbar />
        <Container maxWidth="xl" sx={{ mt: 3 }}>
          <Outlet />
        </Container>
      </Box>
    </Box>
  )
}
