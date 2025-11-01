/**
 * 客户端唯一标识管理
 * 为每个浏览器/设备生成并持久化一个唯一的客户端ID
 * 用于区分不同用户/设备，避免对话记忆混淆
 */

const CLIENT_ID_KEY = 'consult_client_id'

/**
 * 获取或生成客户端唯一ID
 * 如果不存在，生成新的UUID并保存到localStorage
 */
export function getClientId(): string {
  if (typeof window === 'undefined') {
    // SSR 环境，返回临时ID
    return 'ssr-temp-id'
  }

  try {
    let clientId = localStorage.getItem(CLIENT_ID_KEY)
    
    if (!clientId) {
      // 生成新的UUID v4
      clientId = generateUUID()
      localStorage.setItem(CLIENT_ID_KEY, clientId)
      console.log('[ClientID] 生成新的客户端ID:', clientId)
    } else {
      console.log('[ClientID] 使用已存在的客户端ID:', clientId)
    }
    
    return clientId
  } catch (e) {
    console.error('[ClientID] 获取客户端ID失败:', e)
    // 如果localStorage不可用，生成临时ID
    return `temp-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
  }
}

/**
 * 生成UUID v4
 */
function generateUUID(): string {
  // UUID v4格式: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.random() * 16 | 0
    const v = c === 'x' ? r : (r & 0x3 | 0x8)
    return v.toString(16)
  })
}

/**
 * 重置客户端ID（用于测试或重新生成）
 */
export function resetClientId(): string {
  if (typeof window === 'undefined') {
    return 'ssr-temp-id'
  }
  
  try {
    localStorage.removeItem(CLIENT_ID_KEY)
    return getClientId() // 重新生成
  } catch (e) {
    console.error('[ClientID] 重置客户端ID失败:', e)
    return getClientId()
  }
}

