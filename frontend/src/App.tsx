import { CssBaseline, ThemeProvider, createTheme } from '@mui/material'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ColumnProfilePage from './pages/ColumnProfilePage'
import ExportPage from './pages/ExportPage'
import FAIRScorePage from './pages/FAIRScorePage'
import MetadataWizardPage from './pages/MetadataWizardPage'
import OverviewPage from './pages/OverviewPage'
import UploadPage from './pages/UploadPage'
import VCGPage from './pages/VCGPage'
import VCGWizardPage from './pages/VCGWizardPage'
import VCGResultsPage from './pages/VCGResultsPage'
import PaperImportPage from './pages/PaperImportPage'
import TemplateSelectorPage from './pages/TemplateSelectorPage'

const theme = createTheme({
  palette: {
    primary: { main: '#1976d2' },
    secondary: { main: '#0288d1' },
    background: { default: '#f5f7fa' },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h4: { fontWeight: 700 },
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
  },
  shape: { borderRadius: 10 },
  components: {
    MuiCard: {
      styleOverrides: {
        root: { boxShadow: '0 2px 12px rgba(0,0,0,0.08)' },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 600 },
      },
    },
  },
})

export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<UploadPage />} />
            <Route path="overview" element={<OverviewPage />} />
            <Route path="columns" element={<ColumnProfilePage />} />
            <Route path="fair-score" element={<FAIRScorePage />} />
            <Route path="metadata" element={<MetadataWizardPage />} />
            <Route path="templates" element={<TemplateSelectorPage />} />
            <Route path="export" element={<ExportPage />} />
            <Route path="vcg" element={<VCGPage />} />
            <Route path="vcg/wizard" element={<VCGWizardPage />} />
            <Route path="vcg/results" element={<VCGResultsPage />} />
            <Route path="paper-import" element={<PaperImportPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  )
}
