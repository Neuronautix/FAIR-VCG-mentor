import SendIcon from '@mui/icons-material/Send'
import { Box, Button, CircularProgress, IconButton, Paper, TextField, Typography } from '@mui/material'
import { useEffect, useRef, useState } from 'react'
import type { ChatMessage } from '../store/useStore'

interface Props {
  messages: ChatMessage[]
  onSend: (text: string) => void
  disabled?: boolean
  loading?: boolean
}

function renderContent(content: string) {
  // Simple markdown: **bold** and `code`
  const parts = content.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <Box
          key={i}
          component="code"
          sx={{ fontFamily: 'monospace', background: 'rgba(0,0,0,0.08)', px: 0.5, borderRadius: 0.5 }}
        >
          {part.slice(1, -1)}
        </Box>
      )
    }
    return <span key={i}>{part}</span>
  })
}

export default function ChatInterface({ messages, onSend, disabled = false, loading = false }: Props) {
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const lastAgentMessage = [...messages].reverse().find(m => m.role === 'agent')
  const quickOptions = lastAgentMessage?.options && lastAgentMessage.options.length > 0
    ? lastAgentMessage.options
    : []

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Message list */}
      <Box
        sx={{
          flexGrow: 1,
          overflowY: 'auto',
          maxHeight: 500,
          display: 'flex',
          flexDirection: 'column',
          gap: 1,
          p: 2,
          background: '#f9fafc',
          borderRadius: 2,
          border: '1px solid rgba(0,0,0,0.08)',
          mb: 1,
        }}
      >
        {messages.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 4 }}>
            The AI assistant will guide you through VCG configuration.
          </Typography>
        )}

        {messages.map((msg, idx) => {
          const isAgent = msg.role === 'agent'
          return (
            <Box
              key={idx}
              sx={{
                display: 'flex',
                justifyContent: isAgent ? 'flex-start' : 'flex-end',
              }}
            >
              <Paper
                elevation={0}
                sx={{
                  maxWidth: '75%',
                  px: 2,
                  py: 1,
                  borderRadius: isAgent ? '4px 16px 16px 16px' : '16px 4px 16px 16px',
                  background: isAgent ? '#e3f2fd' : '#1976d2',
                  color: isAgent ? 'text.primary' : 'white',
                }}
              >
                <Typography variant="body2" component="div">
                  {renderContent(msg.content)}
                </Typography>
              </Paper>
            </Box>
          )
        })}

        {/* Typing indicator */}
        {loading && (
          <Box sx={{ display: 'flex', justifyContent: 'flex-start' }}>
            <Paper
              elevation={0}
              sx={{ px: 2, py: 1, borderRadius: '4px 16px 16px 16px', background: '#e3f2fd', display: 'flex', alignItems: 'center', gap: 1 }}
            >
              <CircularProgress size={16} />
              <Typography variant="body2" color="text.secondary">Thinking…</Typography>
            </Paper>
          </Box>
        )}

        <div ref={bottomRef} />
      </Box>

      {/* Quick reply options */}
      {quickOptions.length > 0 && !disabled && (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1 }}>
          {quickOptions.map((opt, i) => (
            <Button
              key={i}
              size="small"
              variant="outlined"
              onClick={() => onSend(opt)}
              disabled={disabled || loading}
              sx={{ textTransform: 'none' }}
            >
              {opt}
            </Button>
          ))}
        </Box>
      )}

      {/* Text input */}
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
        <TextField
          fullWidth
          multiline
          maxRows={4}
          size="small"
          placeholder="Type a message…"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled || loading}
          variant="outlined"
        />
        <IconButton
          color="primary"
          onClick={handleSend}
          disabled={disabled || loading || !input.trim()}
          sx={{ mb: 0.5 }}
        >
          <SendIcon />
        </IconButton>
      </Box>
    </Box>
  )
}
