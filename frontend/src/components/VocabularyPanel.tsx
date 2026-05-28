import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import RefreshIcon from '@mui/icons-material/Refresh'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import VerifiedIcon from '@mui/icons-material/Verified'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { useEffect, useRef, useState } from 'react'
import {
  discoverVocabFromPDF,
  getVocabulary,
  listHITLSuggestions,
  validateVocabulary,
} from '../api/client'
import { useStore } from '../store/useStore'

const SECTION_LABELS: Array<[keyof import('../api/client').Vocabulary, string]> = [
  ['column_names', 'Column names'],
  ['semantic_types', 'Semantic types'],
  ['units', 'Units'],
  ['metadata_keys', 'Metadata keys'],
  ['licenses', 'Licenses'],
  ['study_types', 'Study types'],
]

export default function VocabularyPanel() {
  const { datasetId, vocabulary, setVocabulary, aiConfigured, setHITLSuggestions } = useStore()
  const [loading, setLoading] = useState(false)
  const [validating, setValidating] = useState(false)
  const [discovering, setDiscovering] = useState(false)
  const [message, setMessage] = useState<{ kind: 'info' | 'success' | 'error'; text: string } | null>(null)
  const fileInput = useRef<HTMLInputElement | null>(null)

  const refresh = async () => {
    if (!datasetId) return
    setLoading(true)
    try {
      const v = await getVocabulary(datasetId)
      setVocabulary(v)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!datasetId) return
    if (!vocabulary) refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId])

  const handleValidate = async () => {
    if (!datasetId) return
    setValidating(true)
    setMessage(null)
    try {
      const res = await validateVocabulary(datasetId)
      setVocabulary(res.vocabulary)
      // Re-fetch HITL queue to surface 'stale' status on older items.
      const fresh = await listHITLSuggestions(datasetId)
      setHITLSuggestions(fresh)
      setMessage({
        kind: 'success',
        text: `Vocabulary validated (v${res.vocabulary.version}). ${
          res.marked_stale > 0
            ? `${res.marked_stale} older suggestion${res.marked_stale === 1 ? '' : 's'} marked stale.`
            : ''
        }`,
      })
    } catch (e: any) {
      setMessage({ kind: 'error', text: e?.response?.data?.detail ?? 'Could not validate vocabulary.' })
    } finally {
      setValidating(false)
    }
  }

  const handleDiscover = async (file: File) => {
    if (!datasetId) return
    setDiscovering(true)
    setMessage(null)
    try {
      const res = await discoverVocabFromPDF(datasetId, file)
      if (res.created.length === 0) {
        setMessage({ kind: 'info', text: 'No new vocabulary terms proposed.' })
      } else {
        setMessage({
          kind: 'success',
          text: `${res.created.length} proposed extension${res.created.length === 1 ? '' : 's'} added to the HITL queue for your approval.`,
        })
      }
      const fresh = await listHITLSuggestions(datasetId)
      setHITLSuggestions(fresh)
    } catch (e: any) {
      setMessage({
        kind: 'error',
        text: e?.response?.data?.detail ?? 'Discovery failed.',
      })
    } finally {
      setDiscovering(false)
    }
  }

  if (!vocabulary) {
    return (
      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="body2" color="text.secondary">
            Loading vocabulary…
          </Typography>
        </CardContent>
      </Card>
    )
  }

  const totalTerms =
    vocabulary.column_names.length +
    vocabulary.semantic_types.length +
    vocabulary.units.length +
    vocabulary.metadata_keys.length +
    vocabulary.licenses.length +
    vocabulary.study_types.length +
    Object.values(vocabulary.controlled_values).reduce((a, b) => a + b.length, 0)

  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <VerifiedIcon
            fontSize="small"
            sx={{ mr: 1, color: vocabulary.validated ? 'success.main' : 'text.disabled' }}
          />
          <Typography variant="subtitle1" fontWeight={700} sx={{ flexGrow: 1 }}>
            Controlled vocabulary
          </Typography>
          <Chip
            label={`v${vocabulary.version}`}
            size="small"
            color={vocabulary.validated ? 'success' : 'default'}
            sx={{ mr: 1 }}
          />
          <Tooltip title="Reload">
            <span>
              <Button size="small" onClick={refresh} disabled={loading} startIcon={
                loading ? <CircularProgress size={14} /> : <RefreshIcon fontSize="small" />
              }>
                Reload
              </Button>
            </span>
          </Tooltip>
        </Box>

        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          The vocabulary is the curated set of terms Claude Haiku is constrained to. Every LLM
          tool call uses these enums; any term not listed here either gets dropped or arrives as
          a "schema extension" suggestion that you must approve.
        </Typography>

        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', mb: 1.5 }}>
          <Button
            size="small"
            variant={vocabulary.validated ? 'outlined' : 'contained'}
            color={vocabulary.validated ? 'success' : 'primary'}
            startIcon={
              validating ? <CircularProgress size={14} /> : <CheckCircleIcon fontSize="small" />
            }
            onClick={handleValidate}
            disabled={validating}
          >
            {vocabulary.validated ? 'Re-validate (bump version)' : 'Validate vocabulary'}
          </Button>
          <Button
            size="small"
            variant="outlined"
            startIcon={
              discovering ? <CircularProgress size={14} /> : <UploadFileIcon fontSize="small" />
            }
            onClick={() => fileInput.current?.click()}
            disabled={discovering}
          >
            Discover terms from PDF…
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept="application/pdf"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) handleDiscover(f)
              e.target.value = ''
            }}
          />
          <Chip label={`${totalTerms} term${totalTerms === 1 ? '' : 's'}`} size="small" variant="outlined" />
        </Stack>

        {!vocabulary.validated && (
          <Alert severity="warning" sx={{ mb: 1.5 }} icon={<AutoAwesomeIcon fontSize="small" />}>
            Vocabulary is unvalidated. Review the terms below and click <strong>Validate</strong>{' '}
            to lock the schema. LLM suggestions stamped against this version will be marked stale
            on the next bump.
          </Alert>
        )}

        {message && (
          <Alert severity={message.kind} sx={{ mb: 1.5 }} onClose={() => setMessage(null)}>
            {message.text}
          </Alert>
        )}

        {SECTION_LABELS.map(([key, label]) => {
          const list = vocabulary[key] as string[]
          if (!Array.isArray(list)) return null
          return (
            <Accordion key={String(key)} disableGutters elevation={0} sx={{ '&:before': { display: 'none' } }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="caption" fontWeight={600}>
                  {label} <span style={{ color: '#888' }}>({list.length})</span>
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {list.length === 0 ? (
                    <Typography variant="caption" color="text.secondary">(none)</Typography>
                  ) : (
                    list.slice(0, 200).map((v) => (
                      <Chip key={v} label={v} size="small" variant="outlined" sx={{ fontSize: 11 }} />
                    ))
                  )}
                  {list.length > 200 && (
                    <Chip label={`+${list.length - 200} more`} size="small" />
                  )}
                </Box>
              </AccordionDetails>
            </Accordion>
          )
        })}

        {Object.keys(vocabulary.controlled_values).length > 0 && (
          <Accordion disableGutters elevation={0} sx={{ '&:before': { display: 'none' } }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="caption" fontWeight={600}>
                Controlled values{' '}
                <span style={{ color: '#888' }}>
                  ({Object.keys(vocabulary.controlled_values).length} column
                  {Object.keys(vocabulary.controlled_values).length === 1 ? '' : 's'})
                </span>
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              {Object.entries(vocabulary.controlled_values).map(([col, vals]) => (
                <Box key={col} sx={{ mb: 1 }}>
                  <Typography variant="caption" fontWeight={600}>{col}:</Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                    {vals.map((v) => (
                      <Chip key={v} label={v} size="small" variant="outlined" sx={{ fontSize: 11 }} />
                    ))}
                  </Box>
                </Box>
              ))}
            </AccordionDetails>
          </Accordion>
        )}
      </CardContent>
    </Card>
  )
}
