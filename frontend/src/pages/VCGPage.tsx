import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import { Alert, Box, Button, CircularProgress, Stack, Typography } from '@mui/material'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getVCGResults,
  getVCGStatus,
  listHITLSuggestions,
  requestVCGLLMSuggest,
  respondVCGChat,
  startVCGChat,
  startVCGGeneration,
} from '../api/client'
import AgentStatusBar from '../components/AgentStatusBar'
import ChatInterface from '../components/ChatInterface'
import HITLPanel from '../components/HITLPanel'
import type { ChatMessage } from '../store/useStore'
import { useStore } from '../store/useStore'

export default function VCGPage() {
  const navigate = useNavigate()
  const {
    datasetId,
    vcgConversation,
    vcgStatus,
    addChatMessage,
    setVCGStatus,
    setVCGResults,
    llmEnabled,
    setHITLSuggestions,
  } = useStore()

  const [loading, setLoading] = useState(false)
  const [activeStep, setActiveStep] = useState<string>('')
  const [errorMsg, setErrorMsg] = useState<string>('')
  const [llmSuggesting, setLlmSuggesting] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const requestVCGSuggestion = async () => {
    if (!datasetId) return
    setLlmSuggesting(true)
    try {
      const res = await requestVCGLLMSuggest(datasetId)
      if (res?.agent_msg) addChatMessage(res.agent_msg)
      const fresh = await listHITLSuggestions(datasetId)
      setHITLSuggestions(fresh)
    } finally {
      setLlmSuggesting(false)
    }
  }

  // Start chat on mount if no conversation yet
  useEffect(() => {
    if (!datasetId) return
    if (vcgConversation.length > 0) return

    setLoading(true)
    startVCGChat(datasetId)
      .then((data: ChatMessage) => {
        addChatMessage(data)
      })
      .catch(() => {
        addChatMessage({
          role: 'agent',
          content: 'Hello! I\'ll help you configure a Virtual Control Group. Which column identifies your treatment/control condition?',
          timestamp: new Date().toISOString(),
        })
      })
      .finally(() => setLoading(false))
  }, [datasetId, vcgConversation.length, addChatMessage, setLoading])

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const startPolling = (id: string) => {
    if (pollRef.current) clearInterval(pollRef.current)

    const steps = [
      'Ingestion Agent',
      'Preprocessing Agent',
      'Statistics Agent',
      'Distribution Agent',
      'Sampling Agent',
    ]
    let stepIdx = 0
    setActiveStep(steps[0])

    pollRef.current = setInterval(async () => {
      try {
        const statusData = await getVCGStatus(id)
        const status: string = statusData.vcg_status

        stepIdx = (stepIdx + 1) % steps.length
        setActiveStep(steps[stepIdx])

        if (status === 'done') {
          clearInterval(pollRef.current!)
          pollRef.current = null

          const results = await getVCGResults(id)
          setVCGResults(results)
          setVCGStatus('done')

          addChatMessage({
            role: 'agent',
            content: 'VCG complete! View your results.',
            timestamp: new Date().toISOString(),
          })

          setTimeout(() => navigate('/vcg/results'), 2000)
        } else if (status === 'failed') {
          clearInterval(pollRef.current!)
          pollRef.current = null
          setVCGStatus('failed')
          setErrorMsg('VCG generation failed. Please reconfigure and try again.')
          addChatMessage({
            role: 'agent',
            content: 'VCG generation failed. Please check your configuration and try again.',
            timestamp: new Date().toISOString(),
          })
        }
      } catch {
        // transient error — keep polling
      }
    }, 2000)
  }

  const handleSend = async (text: string) => {
    if (!datasetId) return

    const userMsg: ChatMessage = {
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    }
    addChatMessage(userMsg)
    setLoading(true)

    try {
      const response: ChatMessage = await respondVCGChat(datasetId, text)
      addChatMessage(response)

      // Refresh HITL queue — the LLM orchestrator queues a vcg_config suggestion
      // when it thinks it has enough info. We never auto-start generation; the
      // user must approve in the HITL panel.
      const fresh = await listHITLSuggestions(datasetId)
      setHITLSuggestions(fresh)

      if (response.ready_to_build) {
        setVCGStatus('running')
        await startVCGGeneration(datasetId)
        startPolling(datasetId)
      }
    } catch {
      addChatMessage({
        role: 'agent',
        content: 'Sorry, something went wrong. Please try again.',
        timestamp: new Date().toISOString(),
      })
    } finally {
      setLoading(false)
    }
  }

  const handleVCGApproved = async () => {
    if (!datasetId) return
    setVCGStatus('running')
    addChatMessage({
      role: 'agent',
      content: 'Configuration approved. Starting VCG generation…',
      timestamp: new Date().toISOString(),
    })
    await startVCGGeneration(datasetId)
    startPolling(datasetId)
  }

  if (!datasetId) {
    return (
      <Alert severity="info" sx={{ mt: 2 }}>
        No dataset loaded. Please upload a CSV first.
      </Alert>
    )
  }

  const chatDisabled = vcgStatus === 'running' || vcgStatus === 'done'

  return (
    <Box>
      {/* Header row */}
      <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 3 }}>
        <Box>
          <Typography variant="h5">Virtual Control Group — AI Assistant</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {llmEnabled
              ? 'Chat with the configured LLM to configure the VCG. The proposed configuration is queued for your approval below before any generation runs.'
              : 'Answer the agent\'s questions to configure and generate a synthetic control group for your dataset.'}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} sx={{ ml: 2, flexShrink: 0 }}>
          {llmEnabled && (
            <Button
              variant="outlined"
              startIcon={llmSuggesting ? <CircularProgress size={16} /> : <AutoAwesomeIcon />}
              onClick={requestVCGSuggestion}
              disabled={llmSuggesting || chatDisabled}
            >
              One-shot LLM proposal
            </Button>
          )}
          <Button variant="outlined" onClick={() => navigate('/vcg/wizard')}>
            Open Wizard
          </Button>
        </Stack>
      </Box>

      {/* HITL panel — proposed configs must be approved before generation runs */}
      <HITLPanel
        category="vcg_config"
        title="Proposed VCG configurations — Human approval required"
        emptyHint={
          llmEnabled
            ? 'The configured LLM will queue a configuration here once it has enough information from the chat. You may also click "One-shot LLM proposal" above.'
            : 'No AI proposals yet. Use the wizard or chat to configure the VCG manually.'
        }
        onApplied={handleVCGApproved}
      />

      {/* Chat */}
      <ChatInterface
        messages={vcgConversation}
        onSend={handleSend}
        disabled={chatDisabled}
        loading={loading}
      />

      {/* Status bar */}
      <AgentStatusBar
        status={vcgStatus}
        activeStep={activeStep}
        errorMessage={errorMsg}
      />

      {/* View Results button */}
      <Box sx={{ mt: 2 }}>
        <Button
          variant="contained"
          disabled={vcgStatus !== 'done'}
          onClick={() => navigate('/vcg/results')}
        >
          View Results
        </Button>
      </Box>
    </Box>
  )
}
