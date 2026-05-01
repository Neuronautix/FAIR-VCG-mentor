import DownloadIcon from '@mui/icons-material/Download'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Collapse,
  Grid,
  IconButton,
  LinearProgress,
  Paper,
  Tooltip,
  Typography,
} from '@mui/material'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getVCGResults, getVCGStatus, vcgExportUrl } from '../api/client'
import AgentStatusBar from '../components/AgentStatusBar'
import CovariateBalanceTable from '../components/CovariateBalanceTable'
import ReliabilityBadge from '../components/ReliabilityBadge'
import { useStore } from '../store/useStore'

const LOADING_STEPS = [
  'Validating data…',
  'Standardising columns…',
  'Fitting distributions…',
  'Sampling synthetic controls…',
  'Computing statistics…',
]

function deriveReliabilityScore(results: {
  balance_report: {
    covariates: Array<{ col: string; smd: number; balance_label: string }>
    outcomes: Array<{ col: string; mean_real: number; sd_real: number; mean_vcg: number; sd_vcg: number; p_value: number }>
  }
}): number {
  const { covariates, outcomes } = results.balance_report
  if (covariates.length === 0 && outcomes.length === 0) return 0.5

  const covScore =
    covariates.length === 0
      ? 1
      : covariates.filter((c) => c.smd < 0.25).length / covariates.length

  const outScore =
    outcomes.length === 0
      ? 1
      : outcomes.filter((o) => o.p_value > 0.05).length / outcomes.length

  return (covScore + outScore) / 2
}

export default function VCGResultsPage() {
  const navigate = useNavigate()
  const { datasetId, vcgStatus, vcgResults, setVCGStatus, setVCGResults } = useStore()

  const [loadingStep, setLoadingStep] = useState(LOADING_STEPS[0])
  const [reportExpanded, setReportExpanded] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const stepRef = useRef(0)

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  useEffect(() => {
    if (vcgStatus === 'running' && datasetId) {
      // Cycle loading text
      const textInterval = setInterval(() => {
        stepRef.current = (stepRef.current + 1) % LOADING_STEPS.length
        setLoadingStep(LOADING_STEPS[stepRef.current])
      }, 2000)

      // Poll status
      pollRef.current = setInterval(async () => {
        try {
          const statusData = await getVCGStatus(datasetId)
          const status: string = statusData.status ?? statusData

          if (status === 'done') {
            clearInterval(pollRef.current!)
            clearInterval(textInterval)
            pollRef.current = null

            const results = await getVCGResults(datasetId)
            setVCGResults(results)
            setVCGStatus('done')
          } else if (status === 'failed') {
            clearInterval(pollRef.current!)
            clearInterval(textInterval)
            pollRef.current = null
            setVCGStatus('failed')
          }
        } catch {
          // transient — keep polling
        }
      }, 2000)

      return () => {
        clearInterval(textInterval)
        if (pollRef.current) clearInterval(pollRef.current)
      }
    }
  }, [vcgStatus, datasetId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Redirect to /vcg if no status at all
  if (!vcgStatus) {
    return (
      <Box sx={{ mt: 2 }}>
        <Alert
          severity="info"
          action={
            <Button color="inherit" size="small" onClick={() => navigate('/vcg')}>
              Go to VCG
            </Button>
          }
        >
          No VCG session found. Start a new session from the VCG page.
        </Alert>
      </Box>
    )
  }

  // Running state
  if (vcgStatus === 'running') {
    return (
      <Box sx={{ mt: 4 }}>
        <Typography variant="h5" gutterBottom>
          Virtual Control Group Results
        </Typography>
        <LinearProgress variant="indeterminate" sx={{ mb: 2 }} />
        <Typography variant="body1" color="text.secondary">
          {loadingStep}
        </Typography>
        <AgentStatusBar status="running" activeStep={loadingStep} />
      </Box>
    )
  }

  // Failed state
  if (vcgStatus === 'failed') {
    return (
      <Box sx={{ mt: 4 }}>
        <Typography variant="h5" gutterBottom>
          Virtual Control Group Results
        </Typography>
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => navigate('/vcg')}>
              Try again
            </Button>
          }
        >
          VCG generation failed. Please reconfigure and try again.
        </Alert>
      </Box>
    )
  }

  // Done but no results yet (shouldn't happen in normal flow)
  if (!vcgResults) {
    return (
      <Box sx={{ mt: 4 }}>
        <Typography variant="body2" color="text.secondary">
          Loading results…
        </Typography>
        <LinearProgress sx={{ mt: 1 }} />
      </Box>
    )
  }

  const reliabilityScore = deriveReliabilityScore(vcgResults)
  const { n_subjects_real, n_subjects_vcg, balance_report, diagnostic_plots, stat_report, generated_at } = vcgResults

  const formattedDate = (() => {
    try {
      return new Date(generated_at).toLocaleString()
    } catch {
      return generated_at
    }
  })()

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5">Virtual Control Group Results</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          Generated: {formattedDate}
        </Typography>
      </Box>

      {/* Summary row */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary">
                Real Controls
              </Typography>
              <Typography variant="h4">{n_subjects_real}</Typography>
              <Typography variant="caption" color="text.secondary">
                subjects
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary">
                VCG Subjects
              </Typography>
              <Typography variant="h4">{n_subjects_vcg}</Typography>
              <Typography variant="caption" color="text.secondary">
                synthetic controls
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                Reliability
              </Typography>
              <ReliabilityBadge score={reliabilityScore} />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Diagnostic Plots */}
      {diagnostic_plots && Object.keys(diagnostic_plots).length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Diagnostic Plots
          </Typography>
          <Grid container spacing={2}>
            {diagnostic_plots.dist_overlap && (
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="subtitle1">Distribution Overlap</Typography>
                      <Tooltip title="Download plot">
                        <IconButton
                          size="small"
                          component="a"
                          href={`data:image/png;base64,${diagnostic_plots.dist_overlap}`}
                          download="dist_overlap.png"
                        >
                          <DownloadIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                    <img
                      src={`data:image/png;base64,${diagnostic_plots.dist_overlap}`}
                      alt="Distribution overlap"
                      style={{ width: '100%', borderRadius: 8 }}
                    />
                  </CardContent>
                </Card>
              </Grid>
            )}
            {diagnostic_plots.qq_plot && (
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="subtitle1">QQ Plot</Typography>
                      <Tooltip title="Download plot">
                        <IconButton
                          size="small"
                          component="a"
                          href={`data:image/png;base64,${diagnostic_plots.qq_plot}`}
                          download="qq_plot.png"
                        >
                          <DownloadIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                    <img
                      src={`data:image/png;base64,${diagnostic_plots.qq_plot}`}
                      alt="QQ plot"
                      style={{ width: '100%', borderRadius: 8 }}
                    />
                  </CardContent>
                </Card>
              </Grid>
            )}
            {/* Any additional plots */}
            {Object.entries(diagnostic_plots)
              .filter(([key]) => key !== 'dist_overlap' && key !== 'qq_plot')
              .map(([key, value]) => (
                <Grid item xs={12} md={6} key={key}>
                  <Card>
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                        <Typography variant="subtitle1">{key.replace(/_/g, ' ')}</Typography>
                        <Tooltip title="Download plot">
                          <IconButton
                            size="small"
                            component="a"
                            href={`data:image/png;base64,${value}`}
                            download={`${key}.png`}
                          >
                            <DownloadIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Box>
                      <img
                        src={`data:image/png;base64,${value}`}
                        alt={key}
                        style={{ width: '100%', borderRadius: 8 }}
                      />
                    </CardContent>
                  </Card>
                </Grid>
              ))}
          </Grid>
        </Box>
      )}

      {/* Covariate Balance Table */}
      <Box sx={{ mb: 3 }}>
        <CovariateBalanceTable
          covariates={balance_report.covariates ?? []}
          outcomes={balance_report.outcomes ?? []}
        />
      </Box>

      {/* Statistical Report (collapsible) */}
      {stat_report && (
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="h6">Statistical Report</Typography>
            <Button size="small" onClick={() => setReportExpanded((v) => !v)}>
              {reportExpanded ? 'Collapse' : 'Expand'}
            </Button>
          </Box>
          <Collapse in={reportExpanded}>
            <Paper
              variant="outlined"
              sx={{ p: 2, fontFamily: 'monospace', fontSize: 12, whiteSpace: 'pre-wrap', maxHeight: 400, overflowY: 'auto' }}
            >
              {stat_report}
            </Paper>
          </Collapse>
        </Box>
      )}

      {/* Downloads */}
      {datasetId && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Downloads
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={() => {
                window.location.href = vcgExportUrl(datasetId, 'vcg-csv')
              }}
            >
              Download VCG CSV
            </Button>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={() => {
                window.location.href = vcgExportUrl(datasetId, 'vcg-report')
              }}
            >
              Download Statistical Report
            </Button>
          </Box>
        </Box>
      )}

      {/* Navigation */}
      <Box sx={{ display: 'flex', gap: 2 }}>
        <Button variant="outlined" onClick={() => navigate('/vcg')}>
          Re-configure
        </Button>
        <Button variant="outlined" onClick={() => navigate('/fair-score')}>
          Back to FAIR Score
        </Button>
      </Box>
    </Box>
  )
}
