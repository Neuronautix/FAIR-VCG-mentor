import AddIcon from '@mui/icons-material/Add'
import ArticleIcon from '@mui/icons-material/Article'
import FactCheckIcon from '@mui/icons-material/FactCheck'
import SchemaIcon from '@mui/icons-material/Schema'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import {
  addStudyCorpusPaper,
  getStudyCorpus,
  listHITLSuggestions,
  requestCorpusSchemaReview,
  StudyCorpus,
  StudyCorpusSourceType,
} from '../api/client'
import HITLPanel from '../components/HITLPanel'
import { useStore } from '../store/useStore'

const SOURCE_TYPES: StudyCorpusSourceType[] = ['doi', 'pdf', 'text']

export default function StudyCorpusPage() {
  const { datasetId, setHITLSuggestions } = useStore()
  const [corpus, setCorpus] = useState<StudyCorpus | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sourceType, setSourceType] = useState<StudyCorpusSourceType>('doi')
  const [sourceRef, setSourceRef] = useState('')
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')

  const load = async () => {
    if (!datasetId) return
    setLoading(true)
    setError(null)
    try {
      const data = await getStudyCorpus(datasetId)
      setCorpus(data)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err.message ?? 'Could not load study corpus.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId])

  const paperCount = corpus?.papers.length ?? 0
  const candidateCount = corpus?.article_schema_candidates.length ?? 0
  const openConflicts = useMemo(
    () => (corpus?.conflicts ?? []).filter((c) => c.status !== 'resolved'),
    [corpus],
  )

  const addPaper = async () => {
    if (!datasetId || !sourceRef.trim()) return
    setSaving(true)
    setError(null)
    try {
      const res = await addStudyCorpusPaper(datasetId, {
        source_type: sourceType,
        source_ref: sourceRef.trim(),
        title: title.trim() || null,
        text: sourceType === 'text' ? text.trim() : null,
      })
      setCorpus(res.corpus)
      setSourceRef('')
      setTitle('')
      setText('')
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err.message ?? 'Could not add paper.')
    } finally {
      setSaving(false)
    }
  }

  const requestReview = async () => {
    if (!datasetId) return
    setReviewing(true)
    setError(null)
    try {
      await requestCorpusSchemaReview(datasetId)
      const fresh = await listHITLSuggestions(datasetId)
      setHITLSuggestions(fresh)
      await load()
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err.message ?? 'Could not request schema review.')
    } finally {
      setReviewing(false)
    }
  }

  if (!datasetId) {
    return (
      <Alert severity="info">
        Upload a dataset before building a study corpus for schema synthesis.
      </Alert>
    )
  }

  return (
    <Box>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
              <ArticleIcon color="primary" />
              <Typography variant="h6">Study Corpus</Typography>
            </Stack>
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              <Chip label={`${paperCount} papers`} size="small" />
              <Chip label={`${candidateCount} article schemas`} size="small" />
              <Chip
                label={`${openConflicts.length} open conflicts`}
                size="small"
                color={openConflicts.length ? 'warning' : 'default'}
              />
            </Stack>
          </CardContent>
        </Card>

        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
              <SchemaIcon color="primary" />
              <Typography variant="h6">Consensus Schema</Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              {Object.keys(corpus?.consensus_schema ?? {}).length
                ? `${Object.keys(corpus?.consensus_schema?.schema ?? {}).length} top-level fields`
                : 'No approved consensus fields yet'}
            </Typography>
          </CardContent>
        </Card>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
            <AddIcon color="primary" />
            <Typography variant="subtitle1" fontWeight={700}>
              Add Paper Source
            </Typography>
          </Stack>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
            <TextField
              select
              size="small"
              label="Source"
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value as StudyCorpusSourceType)}
              sx={{ minWidth: 120 }}
            >
              {SOURCE_TYPES.map((type) => (
                <MenuItem key={type} value={type}>
                  {type.toUpperCase()}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              label={sourceType === 'doi' ? 'DOI' : sourceType === 'pdf' ? 'PDF reference' : 'Text reference'}
              value={sourceRef}
              onChange={(e) => setSourceRef(e.target.value)}
              sx={{ flex: 1 }}
            />
            <TextField
              size="small"
              label="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              sx={{ flex: 1 }}
            />
            <Button
              variant="contained"
              startIcon={saving ? <CircularProgress size={16} /> : <AddIcon />}
              disabled={saving || !sourceRef.trim()}
              onClick={addPaper}
            >
              Add
            </Button>
          </Stack>
          {sourceType === 'text' && (
            <TextField
              multiline
              minRows={4}
              fullWidth
              label="Methods or dataset description"
              value={text}
              onChange={(e) => setText(e.target.value)}
              sx={{ mt: 1.5 }}
            />
          )}
        </CardContent>
      </Card>

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <FactCheckIcon color="primary" />
            <Typography variant="subtitle1" fontWeight={700} sx={{ flexGrow: 1 }}>
              Paper Sources
            </Typography>
            <Button
              variant="outlined"
              startIcon={reviewing ? <CircularProgress size={16} /> : <FactCheckIcon />}
              disabled={reviewing || loading || paperCount === 0}
              onClick={requestReview}
            >
              Schema Review
            </Button>
          </Stack>
          {loading && <CircularProgress size={20} />}
          {!loading && paperCount === 0 && (
            <Typography variant="body2" color="text.secondary">
              No paper sources have been added.
            </Typography>
          )}
          <Stack spacing={1}>
            {(corpus?.papers ?? []).map((paper) => (
              <Box key={paper.id}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
                  <Chip label={paper.source_type.toUpperCase()} size="small" variant="outlined" />
                  <Typography variant="body2" fontWeight={600} sx={{ flex: 1 }}>
                    {paper.title || paper.source_ref}
                  </Typography>
                  <Chip label={paper.status} size="small" />
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  {paper.source_ref}
                </Typography>
                <Divider sx={{ mt: 1 }} />
              </Box>
            ))}
          </Stack>
        </CardContent>
      </Card>

      <HITLPanel
        title="Scientific schema review"
        emptyHint="No schema review questions are pending."
        refreshAction={{ label: 'Schema Review', onClick: requestReview, pending: reviewing }}
        onApplied={load}
      />
    </Box>
  )
}
