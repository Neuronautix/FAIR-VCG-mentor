import DownloadIcon from '@mui/icons-material/Download'
import FolderZipIcon from '@mui/icons-material/FolderZip'
import RefreshIcon from '@mui/icons-material/Refresh'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  Grid,
  LinearProgress,
  Snackbar,
  Typography,
} from '@mui/material'
import { useState } from 'react'
import { getFairScore } from '../api/client'
import { exportUrl } from '../api/client'
import { arriveExportUrl } from '../api/client'
import FAIRScoreBreakdown from '../components/FAIRScoreBreakdown'
import { useStore } from '../store/useStore'

interface ExportItem {
  label: string
  description: string
  endpoint: string
  filename: string
  mime: string
  highlight?: boolean
}

const EXPORTS: ExportItem[] = [
  {
    label: 'Original CSV',
    description: 'Your uploaded file, unchanged.',
    endpoint: 'cleaned-csv',
    filename: 'original_data.csv',
    mime: 'text/csv',
  },
  {
    label: 'Cleaned CSV',
    description: 'Normalized column names and consistent value encoding.',
    endpoint: 'cleaned-csv',
    filename: 'cleaned_data.csv',
    mime: 'text/csv',
    highlight: true,
  },
  {
    label: 'Data Dictionary',
    description: 'CSV with label, description, unit, allowed values, and URI per column.',
    endpoint: 'data-dictionary',
    filename: 'data_dictionary.csv',
    mime: 'text/csv',
    highlight: true,
  },
  {
    label: 'Frictionless datapackage.json',
    description: 'W3C-compatible tabular data package with Table Schema.',
    endpoint: 'frictionless',
    filename: 'datapackage.json',
    mime: 'application/json',
  },
  {
    label: 'CSVW Metadata',
    description: 'W3C CSV on the Web metadata for machine-readable column descriptions.',
    endpoint: 'csvw',
    filename: 'csvw_metadata.json',
    mime: 'application/json',
  },
  {
    label: 'JSON-LD Metadata',
    description: 'Schema.org dataset description, linked data ready.',
    endpoint: 'jsonld',
    filename: 'metadata.jsonld',
    mime: 'application/ld+json',
  },
  {
    label: 'FAIR-Readiness Report',
    description: 'Markdown report with score breakdown, issues, and recommendations.',
    endpoint: 'report',
    filename: 'fair_readiness_report.md',
    mime: 'text/markdown',
    highlight: true,
  },
  {
    label: 'RO-Crate ZIP',
    description: 'Complete research object: all files + ro-crate-metadata.json.',
    endpoint: 'rocrate',
    filename: 'ro-crate.zip',
    mime: 'application/zip',
    highlight: true,
  },
]

function ExportButton({ item, datasetId }: { item: ExportItem; datasetId: string }) {
  const [loading, setLoading] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const handleDownload = async () => {
    setLoading(true)
    setExportError(null)
    try {
      const url = exportUrl(datasetId, item.endpoint)
      const resp = await fetch(url)
      if (!resp.ok) throw new Error('Export failed')
      const blob = await resp.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = item.filename
      a.click()
      URL.revokeObjectURL(a.href)
    } catch {
      setExportError('Export failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card
      variant="outlined"
      sx={{
        mb: 1.5,
        border: item.highlight ? '1.5px solid #1976d2' : undefined,
        background: item.highlight ? '#f5f8ff' : 'white',
      }}
    >
      <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle2" fontWeight={700}>
              {item.label}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {item.description}
            </Typography>
          </Box>
          <Button
            variant={item.highlight ? 'contained' : 'outlined'}
            size="small"
            startIcon={
              loading ? (
                <CircularProgress size={14} color="inherit" />
              ) : item.endpoint === 'rocrate' ? (
                <FolderZipIcon />
              ) : (
                <DownloadIcon />
              )
            }
            onClick={handleDownload}
            disabled={loading}
            sx={{ whiteSpace: 'nowrap' }}
          >
            Download
          </Button>
        </Box>
        {exportError && (
          <Alert severity="error" sx={{ mt: 1 }} onClose={() => setExportError(null)}>
            {exportError}
          </Alert>
        )}
      </CardContent>
      <Snackbar
        open={!!exportError}
        autoHideDuration={5000}
        onClose={() => setExportError(null)}
        message={exportError}
      />
    </Card>
  )
}

function ARRIVEExportCard({ datasetId }: { datasetId: string }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleDownload = async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch(arriveExportUrl(datasetId))
      if (!resp.ok) throw new Error('Export failed')
      const blob = await resp.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = 'arrive_guidelines.zip'
      a.click()
      URL.revokeObjectURL(a.href)
    } catch {
      setError('ARRIVE export failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card sx={{ mt: 2, border: '1.5px solid #2e7d32', background: '#f1f8f1' }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          ARRIVE 2.0 Guidelines Export
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Downloads a ZIP containing two pre-filled Markdown documents:
        </Typography>
        <Box component="ul" sx={{ pl: 2.5, mb: 1.5, '& li': { mb: 0.5 } }}>
          <li>
            <Typography variant="body2">
              <strong>arrive_study_plan.md</strong> — pre-study plan template filled with your dataset
              metadata, animal information, experimental groups, and VCG statistics (if generated).
            </Typography>
          </li>
          <li>
            <Typography variant="body2">
              <strong>arrive_checklist.md</strong> — ARRIVE 2.0 author checklist (Essential 10 + Recommended Set)
              with auto-detected status (✅ / ⚠️ / ❌) per item, pre-filled section references, and
              an action list of missing items.
            </Typography>
          </li>
        </Box>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
          Based on the official ARRIVE 2.0 Author Checklist and ARRIVE Study Plan template
          (www.ARRIVEguidelines.org).
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        <Button
          variant="contained"
          color="success"
          startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <FolderZipIcon />}
          onClick={handleDownload}
          disabled={loading}
        >
          {loading ? 'Generating…' : 'Download ARRIVE ZIP'}
        </Button>
      </CardContent>
    </Card>
  )
}

export default function ExportPage() {
  const { datasetId, fairScore, metadata, importInfo, setFairScore } = useStore()
  const [refreshing, setRefreshing] = useState(false)

  if (!datasetId) {
    return <Alert severity="info">No dataset loaded. Please upload a CSV first.</Alert>
  }

  const handleRefreshScore = async () => {
    setRefreshing(true)
    try {
      const score = await getFairScore(datasetId)
      setFairScore(score)
    } finally {
      setRefreshing(false)
    }
  }

  const title = metadata.title || importInfo?.filename || 'Your dataset'

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Export
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Download individual files or the complete RO-Crate package containing all artifacts.
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={7}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Export Files
              </Typography>
              <Alert severity="info" sx={{ mb: 2 }}>
                The <strong>highlighted</strong> exports have the highest educational and reuse value: the
                data dictionary, the cleaned CSV, the report, and the RO-Crate package.
              </Alert>
              {EXPORTS.map((item) => (
                <ExportButton key={item.endpoint + item.filename} item={item} datasetId={datasetId} />
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                What is in the RO-Crate?
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                The RO-Crate ZIP packages all export files together with a{' '}
                <code>ro-crate-metadata.json</code> file — a JSON-LD document that describes the
                research object and all its files in a machine-readable way, conforming to the
                RO-Crate 1.2 specification.
              </Typography>
              <Typography variant="body2" color="text.secondary">
                This is appropriate when you want to archive the dataset, share it with a repository,
                or submit it as a research output with rich, structured metadata.
              </Typography>
            </CardContent>
          </Card>

          <ARRIVEExportCard datasetId={datasetId} />
        </Grid>

        <Grid item xs={12} md={5}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                <Typography variant="h6">Current FAIR Score</Typography>
                <Button
                  size="small"
                  startIcon={refreshing ? <CircularProgress size={14} /> : <RefreshIcon />}
                  onClick={handleRefreshScore}
                  disabled={refreshing}
                >
                  Refresh
                </Button>
              </Box>
              {fairScore ? (
                <FAIRScoreBreakdown score={fairScore} />
              ) : (
                <Box sx={{ textAlign: 'center', py: 3 }}>
                  <Button variant="outlined" onClick={handleRefreshScore} disabled={refreshing}>
                    Calculate FAIR Score
                  </Button>
                </Box>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Summary
              </Typography>
              <Typography variant="body2" gutterBottom>
                <strong>{title}</strong>
              </Typography>
              {metadata.creator && (
                <Typography variant="body2" color="text.secondary">
                  Creator: {metadata.creator}
                </Typography>
              )}
              {metadata.license && (
                <Typography variant="body2" color="text.secondary">
                  License: {metadata.license}
                </Typography>
              )}
              {metadata.species && (
                <Typography variant="body2" color="text.secondary">
                  Species: {metadata.species}
                </Typography>
              )}
              {!metadata.title && (
                <Alert severity="warning" sx={{ mt: 1 }}>
                  No title set. Complete the Metadata Wizard for richer exports.
                </Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}
