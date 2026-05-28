import DownloadIcon from '@mui/icons-material/Download'
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
  Snackbar,
  Typography,
} from '@mui/material'
import { useState } from 'react'
import { getFairScore } from '../api/client'
import { exportUrl, arriveReportUrl, prepareReportUrl, fairReportUrl } from '../api/client'
import FAIRScoreBreakdown from '../components/FAIRScoreBreakdown'
import { useStore } from '../store/useStore'

interface ExportItem {
  label: string
  description: string
  url: (id: string) => string
  filename: string
  mime: string
  highlight?: boolean
  badge?: string
}

function getExports(id: string): ExportItem[] {
  return [
    {
      label: 'Cleaned CSV',
      description: 'Normalized column names and consistent value encoding.',
      url: (id) => exportUrl(id, 'cleaned-csv'),
      filename: 'cleaned_data.csv',
      mime: 'text/csv',
      highlight: true,
    },
    {
      label: 'Data Dictionary',
      description: 'CSV with label, description, unit, allowed values per column.',
      url: (id) => exportUrl(id, 'data-dictionary'),
      filename: 'data_dictionary.csv',
      mime: 'text/csv',
      highlight: true,
    },
    {
      label: 'FAIR-Readiness Report',
      description: 'Markdown report with FAIR score breakdown, issues, and recommendations.',
      url: fairReportUrl,
      filename: 'fair_readiness_report.md',
      mime: 'text/markdown',
      highlight: true,
    },
    {
      label: 'ARRIVE 2.0 Conformance Report',
      description: 'Reporting completeness assessment — which ARRIVE 2.0 fields are satisfied.',
      url: arriveReportUrl,
      filename: 'arrive_conformance_report.md',
      mime: 'text/markdown',
      badge: 'ARRIVE 2.0',
    },
    {
      label: 'PREPARE Readiness Report',
      description: 'Study planning readiness assessment — which PREPARE checklist items are addressed.',
      url: prepareReportUrl,
      filename: 'prepare_readiness_report.md',
      mime: 'text/markdown',
      badge: 'PREPARE',
    },
  ]
}

function ExportButton({ item, datasetId }: { item: ExportItem; datasetId: string }) {
  const [loading, setLoading] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const handleDownload = async () => {
    setLoading(true)
    setExportError(null)
    try {
      const url = item.url(datasetId)
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
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="subtitle2" fontWeight={700}>
                {item.label}
              </Typography>
              {item.badge && (
                <Box
                  component="span"
                  sx={{
                    fontSize: 10,
                    fontWeight: 700,
                    px: 0.8,
                    py: 0.2,
                    borderRadius: 1,
                    background: '#e3f2fd',
                    color: '#1565c0',
                  }}
                >
                  {item.badge}
                </Box>
              )}
            </Box>
            <Typography variant="caption" color="text.secondary">
              {item.description}
            </Typography>
          </Box>
          <Button
            variant={item.highlight ? 'contained' : 'outlined'}
            size="small"
            startIcon={loading ? <CircularProgress size={14} color="inherit" /> : <DownloadIcon />}
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
  const exports = getExports(datasetId)

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Export
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Download your cleaned data and assessment reports.
      </Typography>

      <Alert severity="info" sx={{ mb: 3 }}>
        <Typography variant="body2">
          <strong>ARRIVE 2.0</strong> is a reporting completeness assessment — it checks whether
          required reporting fields are present. <strong>PREPARE</strong> is a study planning
          readiness assessment. Neither is regulatory validation or proof of research quality.
        </Typography>
      </Alert>

      <Grid container spacing={3}>
        <Grid item xs={12} md={7}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Export Files
              </Typography>
              <Alert severity="info" sx={{ mb: 2 }}>
                <strong>Highlighted exports</strong> are the most useful: cleaned CSV, data dictionary,
                and the FAIR-readiness report.
              </Alert>
              {exports.map((item) => (
                <ExportButton key={item.filename} item={item} datasetId={datasetId} />
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                About the reports
              </Typography>
              <Divider sx={{ mb: 1.5 }} />
              <Typography variant="body2" color="text.secondary" paragraph>
                <strong>FAIR-Readiness Report:</strong> Describes your dataset's Findable, Accessible,
                Interoperable, and Reusable score with a breakdown of detected issues and recommended
                improvements.
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                <strong>ARRIVE 2.0 Report:</strong> Checks which fields required by the ARRIVE 2.0
                reporting guideline (arriveGuidelines.org) are present in your dataset metadata.
                Assign the ARRIVE 2.0 template on the Templates page for a detailed assessment.
              </Typography>
              <Typography variant="body2" color="text.secondary">
                <strong>PREPARE Report:</strong> Checks which PREPARE study planning checklist items
                (Smith AJ et al., Lab Anim 2018) are addressed in your metadata. Assign a PREPARE
                or ARRIVE-PREPARE crosswalk template for a detailed assessment.
              </Typography>
            </CardContent>
          </Card>
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
