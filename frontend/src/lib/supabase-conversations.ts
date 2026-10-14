/**
 * Supabase Conversations & Messages persistence layer.
 * Saves/loads conversations and messages to/from Supabase so that
 * chat history survives page reloads — just like ChatGPT, Claude, or Gemini.
 */

import { getSupabaseClient } from './supabase'
import type { ChatMessage, AssistantMode, WorkspaceLayout } from '@/components/chat-types'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ConversationRow {
  id: string
  user_id: string
  title: string
  mode: string
  layout: string
  created_at: string
  updated_at: string
}

export interface MessageRow {
  id: string
  conversation_id: string
  user_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  attachments: any
  meta?: any
  created_at: string
}

// ─── Helper: get current user id from localStorage ──────────────────────────

function getCurrentUserId(): string {
  try {
    const raw = localStorage.getItem('chai_auth_user')
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed?.id) return parsed.id
    }
  } catch {}
  return 'guest_default'
}

// ─── Save / Create a Conversation ────────────────────────────────────────────

export async function saveConversation(
  conversationId: string,
  title: string,
  mode: AssistantMode,
  layout: WorkspaceLayout = 'chat',
): Promise<boolean> {
  const client = getSupabaseClient()
  if (!client) return false

  const userId = getCurrentUserId()

  try {
    const { error } = await client.from('conversations').upsert(
      {
        id: conversationId,
        user_id: userId,
        title,
        mode,
        layout,
        updated_at: new Date().toISOString(),
      },
      { onConflict: 'id' },
    )
    if (error) {
      console.warn('[Supabase] saveConversation error:', error.message)
      return false
    }
    return true
  } catch (err) {
    console.warn('[Supabase] saveConversation exception:', err)
    return false
  }
}

// ─── Update Conversation Title ───────────────────────────────────────────────

export async function updateConversationTitle(
  conversationId: string,
  title: string,
): Promise<boolean> {
  const client = getSupabaseClient()
  if (!client) return false

  try {
    const { error } = await client
      .from('conversations')
      .update({ title, updated_at: new Date().toISOString() })
      .eq('id', conversationId)
    if (error) {
      console.warn('[Supabase] updateConversationTitle error:', error.message)
      return false
    }
    return true
  } catch {
    return false
  }
}

// ─── Save a Message ──────────────────────────────────────────────────────────

export async function saveMessage(
  conversationId: string,
  message: ChatMessage,
): Promise<boolean> {
  const client = getSupabaseClient()
  if (!client) return false

  const userId = getCurrentUserId()

  try {
    const { error } = await client.from('messages').upsert(
      {
        id: message.id,
        conversation_id: conversationId,
        user_id: userId,
        role: message.role,
        content: message.content,
        attachments: message.attachments || [],
        created_at: new Date().toISOString(),
      },
      { onConflict: 'id' },
    )
    if (error) {
      console.warn('[Supabase] saveMessage error:', error.message)
      return false
    }

    // Also update the conversation's updated_at timestamp
    await client
      .from('conversations')
      .update({ updated_at: new Date().toISOString() })
      .eq('id', conversationId)
      .then(() => {})

    return true
  } catch (err) {
    console.warn('[Supabase] saveMessage exception:', err)
    return false
  }
}

// ─── Load All Conversations for Current User (Recent First) ──────────────────

export async function loadConversations(): Promise<ConversationRow[]> {
  const client = getSupabaseClient()
  if (!client) return []

  const userId = getCurrentUserId()

  try {
    const { data, error } = await client
      .from('conversations')
      .select('*')
      .eq('user_id', userId)
      .order('updated_at', { ascending: false })
      .limit(50)

    if (error) {
      console.warn('[Supabase] loadConversations error:', error.message)
      return []
    }
    return data || []
  } catch {
    return []
  }
}

// ─── Load Messages for a Conversation ────────────────────────────────────────

export async function loadMessages(conversationId: string): Promise<ChatMessage[]> {
  const client = getSupabaseClient()
  if (!client) return []

  try {
    const { data, error } = await client
      .from('messages')
      .select('*')
      .eq('conversation_id', conversationId)
      .order('created_at', { ascending: true })

    if (error) {
      console.warn('[Supabase] loadMessages error:', error.message)
      return []
    }

    return (data || []).map((row: any) => ({
      id: row.id,
      role: row.role as 'user' | 'assistant',
      content: row.content,
      attachments: row.attachments || [],
    }))
  } catch {
    return []
  }
}

// ─── Delete a Conversation ───────────────────────────────────────────────────

export async function deleteConversation(conversationId: string): Promise<boolean> {
  const client = getSupabaseClient()
  if (!client) return false

  try {
    // Messages cascade-delete via FK constraint
    const { error } = await client
      .from('conversations')
      .delete()
      .eq('id', conversationId)
    if (error) {
      console.warn('[Supabase] deleteConversation error:', error.message)
      return false
    }
    return true
  } catch {
    return false
  }
}

// ─── Load a Single Conversation with its Messages ────────────────────────────

export async function loadConversationWithMessages(
  conversationId: string,
): Promise<{ conversation: ConversationRow; messages: ChatMessage[] } | null> {
  const client = getSupabaseClient()
  if (!client) return null

  try {
    const { data: conv, error: convErr } = await client
      .from('conversations')
      .select('*')
      .eq('id', conversationId)
      .maybeSingle()

    if (convErr || !conv) return null

    const messages = await loadMessages(conversationId)
    return { conversation: conv, messages }
  } catch {
    return null
  }
}
