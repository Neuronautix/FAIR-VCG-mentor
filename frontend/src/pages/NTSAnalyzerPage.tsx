import { useState, useRef } from 'react'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import DownloadIcon from '@mui/icons-material/Download'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  IconButton,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'

// ─── Types ────────────────────────────────────────────────────────────────────

interface CitationEvidence {
  matched_text: string
  context: string
  page: number
  tier: 'doi' | 'full_title' | 'author_year' | 'explicit_name'
}

interface CitationResult {
  cited: boolean
  total_occurrences: number
  evidence: CitationEvidence[]
}

interface Layer1Result {
  arrive: CitationResult
  prepare: CitationResult
}

interface Layer2Field {
  value: string | null
  status: 'found' | 'inferred' | 'missing'
  evidence: string | null
  arrive_field_id: string | null
  prepare_field_id: string | null
}

type Classification = 'BOTH' | 'ARRIVE_ONLY' | 'PREPARE_ONLY' | 'NEITHER' | 'ERROR'

interface NTSResult {
  filename: string
  analyzed_at: string
  classification: Classification
  text_quality?: {
    page_count: number
    total_chars: number
    extraction_warning?: string
  }
  layer1: Layer1Result | null
  layer2: Record<string, Layer2Field> | null
  layer2_available: boolean
  layer2_error?: string | null
  layer1_error?: string | null
  error?: string | null
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function classificationColor(
  c: Classification
): 'success' | 'info' | 'warning' | 'default' | 'error' {
  switch (c) {
    case 'BOTH':
      return 'success'
    case 'ARRIVE_ONLY':
      return 'info'
    case 'PREPARE_ONLY':
      return 'warning'
    case 'NEITHER':
      return 'default'
    case 'ERROR':
      return 'error'
  }
}

function tierLabel(tier: string): string {
  switch (tier) {
    case 'doi':
      return 'DOI'
    case 'full_title':
      return 'Full title'
    case 'author_year':
      return 'Author-year'
    case 'explicit_name':
      return 'Name'
    default:
      return tier
  }
}

function toTitleCase(str: string): string {
  return str.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function truncate(s: string, max = 40): string {
  return s.length > max ? s.slice(0, max) + '…' : s
}

// ─── Layer 2 field groups ─────────────────────────────────────────────────────

const LAYER2_GROUPS: { label: string; fields: string[] }[] = [
  {
    label: 'Study Information',
    fields: ['study_title', 'project_licence', 'regulatory_authority', 'nts_date'],
  },
  {
    label: 'Animals',
    fields: [
      'species',
      'strain',
      'sex',
      'age',
      'total_n',
      'experimental_groups',
      'sample_size_per_group',
    ],
  },
  {
    label: 'Welfare',
    fields: ['severity_classification', 'humane_endpoints', 'adverse_events'],
  },
  {
    label: 'Procedures',
    fields: ['procedures_description', 'outcome_measures'],
  },
  {
    label: '3Rs',
    fields: [
      'three_rs_replacement',
      'three_rs_reduction',
      'three_rs_refinement',
    ],
  },
  {
    label: 'PREPARE Specific',
    fields: [
      'prepare_lay_summary',
      'prepare_harm_benefit',
      'prepare_literature_searches',
    ],
  },
]

// ─── Sub-components ───────────────────────────────────────────────────────────

function CitationEvidenceList({
  label,
  result,
}: {
  label: string
  result: CitationResult | null | undefined
}) {
  if (!result) {
    return (
      <Box mb={2}>
        <Typography variant="subtitle2" fontWeight={700} mb={0.5}>
          {label}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          No data available
        </Typography>
      </Box>
    )
  }

  return (
    <Box mb={2}>
      <Box display="flex" alignItems="center" gap={1} mb={0.75}>
        <Typography variant="subtitle2" fontWeight={700}>
          {label}
        </Typography>
        <Chip
          label={result.cited ? 'Cited' : 'Not cited'}
          color={result.cited ? 'success' : 'default'}
          size="small"
        />
        {result.cited && (
          <Typography variant="caption" color="text.secondary">
            {result.total_occurrences} occurrence{result.total_occurrences !== 1 ? 's' : ''}
          </Typography>
        )}
      </Box>
      {result.evidence.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No citation found
        </Typography>
      ) : (
        <Box display="flex" flexDirection="column" gap={1}>
          {result.evidence.map((ev, i) => (
            <Paper
              key={i}
              variant="outlined"
              sx={{ p: 1.25, borderRadius: 1.5 }}
            >
              <Box display="flex" alignItems="center" gap={1} mb={0.5}>
                <Typography variant="body2" fontWeight={700} sx={{ flex: 1 }}>
                  "{ev.matched_text}"
                </Typography>
                <Chip
                  label={tierLabel(ev.tier)}
                  size="small"
                  variant="outlined"
                  sx={{ flexShrink: 0 }}
                />
                <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                  p.{ev.page}
                </Typography>
              </Box>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ fontStyle: 'italic', display: 'block', lineHeight: 1.4 }}
              >
                {ev.context}
              </Typography>
            </Paper>
          ))}
        </Box>
      )}
    </Box>
  )
}

function Layer2Fields({ layer2 }: { layer2: Record<string, Layer2Field> }) {
  return (
    <Box display="flex" flexDirection="column" gap={2}>
      {LAYER2_GROUPS.map((group) => {
        const groupFields = group.fields.filter((f) => f in layer2)
        if (groupFields.length === 0) return null
        return (
          <Box key={group.label}>
            <Typography
              variant="subtitle2"
              fontWeight={700}
              color="text.secondary"
              sx={{ textTransform: 'uppercase', letterSpacing: 0.5, fontSize: '0.7rem', mb: 0.75 }}
            >
              {group.label}
            </Typography>
            <Box display="flex" flexDirection="column" gap={0.75}>
              {groupFields.map((fieldId) => {
                const field = layer2[fieldId]
                const statusColor: 'success' | 'warning' | 'default' =
                  field.status === 'found'
                    ? 'success'
                    : field.status === 'inferred'
                    ? 'warning'
                    : 'default'
                return (
                  <Box
                    key={fieldId}
                    display="flex"
                    alignItems="flex-start"
                    gap={1}
                    sx={{ py: 0.5, borderBottom: '1px solid', borderColor: 'divider' }}
                  >
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ minWidth: 200, flexShrink: 0, pt: 0.25 }}
                    >
                      {toTitleCase(fieldId)}
                    </Typography>
                    <Typography variant="body2" sx={{ flex: 1, wordBreak: 'break-word' }}>
                      {field.value ?? '—'}
                    </Typography>
                    <Chip
                      label={field.status}
                      color={statusColor}
                      size="small"
                      sx={{ flexShrink: 0 }}
                    />
                  </Box>
                )
              })}
            </Box>
          </Box>
        )
      })}
    </Box>
  )
}

function ExpandedRowContent({ result }: { result: NTSResult }) {
  return (
    <Box sx={{ p: 2.5, bgcolor: 'action.hover', borderRadius: 1 }}>
      {result.layer1_error && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Text extraction failed: {result.layer1_error}. Citation detection may be incomplete.
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Layer 1 */}
        <Grid item xs={12} md={result.layer2_available ? 5 : 12}>
          <Typography variant="subtitle1" fontWeight={700} mb={1.5}>
            Layer 1 — Citation Evidence
          </Typography>
          {result.layer1 ? (
            <>
              <CitationEvidenceList label="ARRIVE" result={result.layer1.arrive} />
              <CitationEvidenceList label="PREPARE" result={result.layer1.prepare} />
            </>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Layer 1 data not available.
            </Typography>
          )}
        </Grid>

        {/* Layer 2 */}
        {(result.layer2_available || result.layer2_error) && (
          <Grid item xs={12} md={7}>
            <Typography variant="subtitle1" fontWeight={700} mb={1.5}>
              Layer 2 — Extracted Metadata
            </Typography>
            {result.layer2_error ? (
              <Alert severity="warning">{result.layer2_error}</Alert>
            ) : result.layer2 ? (
              <Layer2Fields layer2={result.layer2} />
            ) : (
              <Typography variant="body2" color="text.secondary">
                No metadata available.
              </Typography>
            )}
          </Grid>
        )}

        {!result.layer2_available && !result.layer2_error && (
          <Grid item xs={12} md={7}>
            <Typography variant="subtitle1" fontWeight={700} mb={1.5}>
              Layer 2 — Extracted Metadata
            </Typography>
            <Alert severity="info">
              LLM metadata extraction not available. Set ANTHROPIC_API_KEY to enable.
            </Alert>
          </Grid>
        )}
      </Grid>
    </Box>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function NTSAnalyzerPage() {
  const [files, setFiles] = useState<File[]>([])
  const [results, setResults] = useState<NTSResult[]>([])
  const [batchId, setBatchId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedRow, setExpandedRow] = useState<string | null>(null)

  const inputRef = useRef<HTMLInputElement>(null)

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return
    const pdfs = Array.from(incoming).filter((f) =>
      f.name.toLowerCase().endsWith('.pdf')
    )
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name))
      return [...prev, ...pdfs.filter((f) => !names.has(f.name))]
    })
  }

  const removeFile = (name: string) => {
    setFiles((prev) => prev.filter((f) => f.name !== name))
  }

  const handleAnalyze = async () => {
    setLoading(true)
    setError(null)
    setResults([])
    setBatchId(null)
    try {
      const form = new FormData()
      if (files.length === 1) {
        form.append('file', files[0])
        const res = await fetch('/api/nts/analyze', { method: 'POST', body: form })
        if (!res.ok) throw new Error(await res.text())
        const data = await res.json()
        setResults(data.results)
        setBatchId(data.batch_id)
      } else {
        for (const f of files) form.append('files', f)
        const res = await fetch('/api/nts/analyze-batch', { method: 'POST', body: form })
        if (!res.ok) throw new Error(await res.text())
        const data = await res.json()
        setResults(data.results)
        setBatchId(data.batch_id)
      }
    } catch (e: any) {
      setError(e.message ?? 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  // Classification summary counts
  const classificationCounts = results.reduce(
    (acc, r) => {
      acc[r.classification] = (acc[r.classification] ?? 0) + 1
      return acc
    },
    {} as Record<Classification, number>
  )

  return (
    <Box sx={{ maxWidth: 1100, mx: 'auto', py: 4, px: 2 }}>
      {/* ── Header ── */}
      <Typography variant="h5" fontWeight={700} mb={0.75}>
        NTS Citation Analyser
      </Typography>
      <Typography variant="body2" color="text.secondary" mb={3} sx={{ maxWidth: 720 }}>
        Upload one or more Non-Technical Summaries (NTS) as PDF files. The analyser
        deterministically detects citations of the ARRIVE and PREPARE guidelines using pattern
        matching, then optionally extracts structured metadata using an LLM.
      </Typography>

      {/* ── Upload card ── */}
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent sx={{ p: 3 }}>
          {/* Drop zone */}
          <Box
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              addFiles(e.dataTransfer.files)
            }}
            sx={{
              border: '2px dashed',
              borderColor: 'divider',
              borderRadius: 2,
              p: 4,
              textAlign: 'center',
              cursor: 'pointer',
              transition: 'border-color 0.2s, background 0.2s',
              '&:hover': {
                borderColor: 'primary.main',
                bgcolor: 'action.hover',
              },
            }}
          >
            <input
              ref={inputRef}
              type="file"
              multiple
              accept=".pdf"
              style={{ display: 'none' }}
              onChange={(e) => addFiles(e.target.files)}
            />
            <CloudUploadIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
            <Typography variant="body1" fontWeight={500}>
              Drop PDF files here or click to select
            </Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              Non-Technical Summaries (PDF format)
            </Typography>
          </Box>

          {/* Selected file chips */}
          {files.length > 0 && (
            <Box
              mt={2}
              display="flex"
              flexWrap="wrap"
              gap={1}
              sx={{ maxHeight: 120, overflowY: 'auto' }}
            >
              {files.map((f) => (
                <Chip
                  key={f.name}
                  label={truncate(f.name, 45)}
                  onDelete={() => removeFile(f.name)}
                  size="small"
                  variant="outlined"
                />
              ))}
            </Box>
          )}
        </CardContent>
      </Card>

      {/* ── Analyse button ── */}
      <Box mb={3}>
        <Button
          variant="contained"
          size="large"
          disabled={files.length === 0 || loading}
          onClick={handleAnalyze}
          startIcon={loading ? <CircularProgress size={20} color="inherit" /> : undefined}
        >
          {loading
            ? 'Analysing…'
            : `Analyse ${files.length} file${files.length !== 1 ? 's' : ''}`}
        </Button>
      </Box>

      {/* ── Error ── */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* ── Results ── */}
      {results.length > 0 && (
        <Box>
          {/* Summary row */}
          <Box
            display="flex"
            alignItems="center"
            flexWrap="wrap"
            gap={1.5}
            mb={2}
          >
            <Typography variant="subtitle1" fontWeight={600}>
              {results.length} document{results.length !== 1 ? 's' : ''} analysed
            </Typography>

            {(['BOTH', 'ARRIVE_ONLY', 'PREPARE_ONLY', 'NEITHER'] as Classification[])
              .filter((c) => classificationCounts[c] > 0)
              .map((c) => (
                <Chip
                  key={c}
                  label={`${c.replace('_', ' ')}: ${classificationCounts[c]}`}
                  color={classificationColor(c)}
                  size="small"
                />
              ))}

            <Box ml="auto" display="flex" gap={1}>
              <Button
                size="small"
                variant="outlined"
                startIcon={<DownloadIcon />}
                onClick={() => window.open(`/api/nts/export/${batchId}/csv`, '_blank')}
              >
                Export CSV
              </Button>
              <Button
                size="small"
                variant="outlined"
                startIcon={<DownloadIcon />}
                onClick={() => window.open(`/api/nts/export/${batchId}/json`, '_blank')}
              >
                Export JSON
              </Button>
            </Box>
          </Box>

          {/* Results table */}
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: 'action.hover' }}>
                  {[
                    'Document',
                    'ARRIVE',
                    'PREPARE',
                    'Classification',
                    'Species',
                    'Severity',
                    'Pages',
                    'Details',
                  ].map((h) => (
                    <TableCell
                      key={h}
                      sx={{ fontWeight: 700, whiteSpace: 'nowrap', py: 1.25 }}
                    >
                      {h}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {results.map((result) => {
                  const isExpanded = expandedRow === result.filename
                  const arriveCitation = result.layer1?.arrive
                  const prepareCitation = result.layer1?.prepare

                  return (
                    <>
                      <TableRow
                        key={result.filename}
                        hover
                        sx={{
                          cursor: 'pointer',
                          '& td': { verticalAlign: 'middle' },
                          ...(isExpanded
                            ? { bgcolor: 'action.selected' }
                            : {}),
                        }}
                        onClick={() =>
                          setExpandedRow(isExpanded ? null : result.filename)
                        }
                      >
                        {/* Document */}
                        <TableCell sx={{ maxWidth: 240 }}>
                          <Typography
                            variant="body2"
                            fontWeight={500}
                            sx={{ wordBreak: 'break-all' }}
                            title={result.filename}
                          >
                            {truncate(result.filename, 40)}
                          </Typography>
                        </TableCell>

                        {/* ARRIVE */}
                        <TableCell>
                          {arriveCitation != null ? (
                            <Box>
                              <Chip
                                label={arriveCitation.cited ? `Cited (${arriveCitation.total_occurrences}×)` : 'Not cited'}
                                color={arriveCitation.cited ? 'success' : 'default'}
                                size="small"
                              />
                              {arriveCitation.cited &&
                                arriveCitation.evidence.length > 0 && (
                                  <Typography
                                    variant="caption"
                                    color="text.secondary"
                                    display="block"
                                    mt={0.25}
                                  >
                                    via {tierLabel(arriveCitation.evidence[0].tier)}
                                  </Typography>
                                )}
                            </Box>
                          ) : (
                            <Typography variant="body2" color="text.disabled">
                              —
                            </Typography>
                          )}
                        </TableCell>

                        {/* PREPARE */}
                        <TableCell>
                          {prepareCitation != null ? (
                            <Box>
                              <Chip
                                label={prepareCitation.cited ? `Cited (${prepareCitation.total_occurrences}×)` : 'Not cited'}
                                color={prepareCitation.cited ? 'success' : 'default'}
                                size="small"
                              />
                              {prepareCitation.cited &&
                                prepareCitation.evidence.length > 0 && (
                                  <Typography
                                    variant="caption"
                                    color="text.secondary"
                                    display="block"
                                    mt={0.25}
                                  >
                                    via {tierLabel(prepareCitation.evidence[0].tier)}
                                  </Typography>
                                )}
                            </Box>
                          ) : (
                            <Typography variant="body2" color="text.disabled">
                              —
                            </Typography>
                          )}
                        </TableCell>

                        {/* Classification */}
                        <TableCell>
                          <Chip
                            label={result.classification.replace(/_/g, ' ')}
                            color={classificationColor(result.classification)}
                            size="small"
                          />
                        </TableCell>

                        {/* Species */}
                        <TableCell>
                          <Typography variant="body2">
                            {result.layer2?.species?.value ?? '—'}
                          </Typography>
                        </TableCell>

                        {/* Severity */}
                        <TableCell>
                          <Typography variant="body2">
                            {result.layer2?.severity_classification?.value ?? '—'}
                          </Typography>
                        </TableCell>

                        {/* Pages */}
                        <TableCell>
                          <Typography variant="body2">
                            {result.text_quality?.page_count ?? '—'}
                          </Typography>
                        </TableCell>

                        {/* Details toggle */}
                        <TableCell
                          onClick={(e) => {
                            e.stopPropagation()
                            setExpandedRow(isExpanded ? null : result.filename)
                          }}
                        >
                          <IconButton size="small">
                            <ExpandMoreIcon
                              sx={{
                                transform: isExpanded
                                  ? 'rotate(180deg)'
                                  : 'rotate(0deg)',
                                transition: 'transform 0.2s',
                              }}
                            />
                          </IconButton>
                        </TableCell>
                      </TableRow>

                      {/* Expanded details row */}
                      {isExpanded && (
                        <TableRow key={`${result.filename}-details`}>
                          <TableCell colSpan={8} sx={{ p: 0, border: 0 }}>
                            <Box sx={{ px: 2, py: 1.5 }}>
                              <ExpandedRowContent result={result} />
                            </Box>
                          </TableCell>
                        </TableRow>
                      )}
                    </>
                  )
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}
    </Box>
  )
}
