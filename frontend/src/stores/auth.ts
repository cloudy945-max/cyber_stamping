import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { http } from '@/api/http'

const TOKEN_KEY = 'cyber_stamping_token'
const USER_KEY = 'cyber_stamping_user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const username = ref<string | null>(localStorage.getItem(USER_KEY))

  const isAuthenticated = computed(() => !!token.value)

  async function login(user: string, password: string) {
    // 后端 /api/auth/login 接受表单 (application/x-www-form-urlencoded)
    const params = new URLSearchParams({
      username: user,
      password,
      grant_type: 'password',
    })
    const { data } = await http.post('/api/auth/login', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    token.value = data.access_token
    username.value = data.username
    localStorage.setItem(TOKEN_KEY, data.access_token)
    localStorage.setItem(USER_KEY, data.username)
  }

  function logout() {
    token.value = null
    username.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  return { token, username, isAuthenticated, login, logout }
})
