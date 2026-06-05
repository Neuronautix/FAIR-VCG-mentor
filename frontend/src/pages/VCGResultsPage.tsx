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
    if (!datasetId) return
    let cancelled = false
    getVCGStatus(datasetId)
      .then(async (statusData) => {
        if (cancelled) return
        const status: string = statusData.vcg_status ?? statusData.status ?? statusData
        setVCGStatus(status as any)
        if (status === 'done') {
          const results = await getVCGResults(datasetId)
          if (!cancelled) setVCGResults(results)
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [datasetId, setVCGResults, setVCGStatus])

  useEffect(() => {
    if (vcgStatus === 'running' && datasetId) {
      // Cycle loading text
      const textInterval = setInterval(() => {
        stepRef.current = (stepRef.current + 1) % LOADING_STEPS.length
        setLoadingStep(LOADING_STEPS[stepRef.current])
      }, 2000)

      // Poll status
      pollRef.current = setInterval(async () => {
        if (!datasetId) return
        try {
          const statusData = await getVCGStatus(datasetId)
          const status: string = statusData.vcg_status ?? statusData.status ?? statusData

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

  useEffect(() => {
    if (vcgStatus !== 'done' || !datasetId || vcgResults) return
    let cancelled = false
    getVCGResults(datasetId)
      .then((results) => { if (!cancelled) setVCGResults(results) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [vcgStatus, datasetId, vcgResults, setVCGResults])

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
          VCG generation failed. Please reconfigure and try again from the VCG page.
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

  const reliabilityScore: number =
    typeof vcgResults.reliability_score === 'number'
      ? vcgResults.reliability_score
      : deriveReliabilityScore(vcgResults)

  const {
    n_subjects_real,
    n_subjects_vcg,
    balance_report,
    diagnostic_plots,
    per_endpoint_plots,
    reliability_breakdown,
    method_diagnostics,
    stat_report,
    generated_at,
    warnings,
    method_used,
  } = vcgResults

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
              {method_used && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                  Method: {method_used}
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Warnings */}
      {warnings && warnings.length > 0 && (
        <Box sx={{ mb: 3 }}>
          {warnings.map((w: string, i: number) => (
            <Alert key={i} severity="warning" sx={{ mb: 1 }}>
              {w}
            </Alert>
          ))}
        </Box>
      )}

      {/* Reliability breakdown per endpoint */}
      {reliability_breakdown?.per_endpoint && Object.keys(reliability_breakdown.per_endpoint).length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Reliability Breakdown
          </Typography>
          <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f5f5f5' }}>
                  {['Endpoint', 'Mean (real)', 'Mean (VCG)', 'Cohen\'s d', 'KS p-value', 'CI width', 'Verdict'].map((h) => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '1px solid #e0e0e0' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(reliability_breakdown.per_endpoint as Record<string, Record<string, unknown>>).map(([col, ep]) => {
                  const interp = ep.interpretation as string
                  const color = interp === 'Excellent' ? '#2e7d32' : interp === 'Good' ? '#1565c0' : interp === 'Acceptable' ? '#e65100' : '#c62828'
                  return (
                    <tr key={col}>
                      <td style={{ padding: '7px 12px', borderBottom: '1px solid #f0f0f0', fontWeight: 600 }}>{col}</td>
                      <td style={{ padding: '7px 12px', borderBottom: '1px solid #f0f0f0' }}>
                        {typeof ep.mean_real === 'number' ? ep.mean_real.toFixed(3) : '—'} ± {typeof ep.std_real === 'number' ? ep.std_real.toFixed(3) : '—'}
                      </td>
                      <td style={{ padding: '7px 12px', borderBottom: '1px solid #f0f0f0' }}>
                        {typeof ep.mean_vcg === 'number' ? ep.mean_vcg.toFixed(3) : '—'} ± {typeof ep.std_vcg === 'number' ? ep.std_vcg.toFixed(3) : '—'}
                      </td>
                      <td style={{ padding: '7px 12px', borderBottom: '1px solid #f0f0f0' }}>
                        {ep.cohens_d != null ? (ep.cohens_d as number).toFixed(3) : '—'}
                      </td>
                      <td style={{ padding: '7px 12px', borderBottom: '1px solid #f0f0f0' }}>
                        {ep.ks_pvalue != null ? (ep.ks_pvalue as number).toFixed(4) : '—'}
                      </td>
                      <td style={{ padding: '7px 12px', borderBottom: '1px solid #f0f0f0' }}>
                        {ep.ci_width != null ? (ep.ci_width as number).toFixed(3) : '—'}
                      </td>
                      <td style={{ padding: '7px 12px', borderBottom: '1px solid #f0f0f0', color, fontWeight: 600 }}>
                        {interp}
                        <Typography variant="caption" display="block" color="text.secondary">
                          {ep.interpretation_detail as string}
                        </Typography>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </Paper>
        </Box>
      )}

      {/* Diagnostic Plots */}
      {(diagnostic_plots?.dist_overlap || diagnostic_plots?.qq_plot) && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Overview Diagnostic Plots
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
                      <Typography variant="subtitle1">Q-Q Plot</Typography>
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
          </Grid>
        </Box>
      )}

      {/* Per-endpoint diagnostic plots */}
      {per_endpoint_plots && Object.keys(per_endpoint_plots).length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Per-Endpoint Diagnostics
          </Typography>
          {Object.entries(per_endpoint_plots as Record<string, Record<string, string>>).map(([col, plots]) => (
            <Box key={col} sx={{ mb: 2 }}>
              <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 600 }}>{col}</Typography>
              <Grid container spacing={2}>
                {plots.density && (
                  <Grid item xs={12} md={6}>
                    <Card variant="outlined">
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                          <Typography variant="subtitle2">Density Overlay</Typography>
                          <Tooltip title="Download">
                            <IconButton size="small" component="a" href={`data:image/png;base64,${plots.density}`} download={`${col}_density.png`}>
                              <DownloadIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </Box>
                        <img src={`data:image/png;base64,${plots.density}`} alt={`${col} density`} style={{ width: '100%', borderRadius: 6 }} />
                      </CardContent>
                    </Card>
                  </Grid>
                )}
                {plots.qq && (
                  <Grid item xs={12} md={6}>
                    <Card variant="outlined">
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                          <Typography variant="subtitle2">Q-Q Plot</Typography>
                          <Tooltip title="Download">
                            <IconButton size="small" component="a" href={`data:image/png;base64,${plots.qq}`} download={`${col}_qq.png`}>
                              <DownloadIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </Box>
                        <img src={`data:image/png;base64,${plots.qq}`} alt={`${col} qq`} style={{ width: '100%', borderRadius: 6 }} />
                      </CardContent>
                    </Card>
                  </Grid>
                )}
              </Grid>
            </Box>
          ))}
        </Box>
      )}

      {/* Covariate Balance Table */}
      <Box sx={{ mb: 3 }}>
        <CovariateBalanceTable
          covariates={balance_report.covariates ?? []}
          outcomes={balance_report.outcomes ?? []}
        />
      </Box>

      {/* Method diagnostics */}
      {method_diagnostics && (method_diagnostics.fitted_distributions || method_diagnostics.per_column_method) && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Method Diagnostics
          </Typography>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="body2" sx={{ mb: 1 }}>
              <strong>Generation method:</strong> {method_diagnostics.method ?? method_used ?? '—'}
              {method_diagnostics.n_control != null && ` | Real control n = ${method_diagnostics.n_control}`}
            </Typography>
            {method_diagnostics.fitted_distributions && (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: '#f5f5f5' }}>
                    {['Endpoint', 'Distribution', 'AIC', 'BIC', 'Shapiro-W', 'N fitted'].map(h => (
                      <th key={h} style={{ padding: '6px 10px', textAlign: 'left', borderBottom: '1px solid #e0e0e0' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(method_diagnostics.fitted_distributions as Record<string, Record<string, unknown>>).map(([col, d]) => (
                    <tr key={col}>
                      <td style={{ padding: '5px 10px', borderBottom: '1px solid #f0f0f0', fontWeight: 600 }}>{col}</td>
                      <td style={{ padding: '5px 10px', borderBottom: '1px solid #f0f0f0' }}>{d.dist_name as string}</td>
                      <td style={{ padding: '5px 10px', borderBottom: '1px solid #f0f0f0' }}>{d.aic != null ? (d.aic as number).toFixed(2) : '—'}</td>
                      <td style={{ padding: '5px 10px', borderBottom: '1px solid #f0f0f0' }}>{d.bic != null ? (d.bic as number).toFixed(2) : '—'}</td>
                      <td style={{ padding: '5px 10px', borderBottom: '1px solid #f0f0f0' }}>{d.shapiro_w != null ? (d.shapiro_w as number).toFixed(4) : '—'}</td>
                      <td style={{ padding: '5px 10px', borderBottom: '1px solid #f0f0f0' }}>{d.n_fitted as number ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {method_diagnostics.per_column_method && (
              <Box sx={{ mt: 1 }}>
                {Object.entries(method_diagnostics.per_column_method as Record<string, string>).map(([col, m]) => (
                  <Typography key={col} variant="caption" display="block">
                    {col}: <strong>{m}</strong>
                  </Typography>
                ))}
              </Box>
            )}
          </Paper>
        </Box>
      )}

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
