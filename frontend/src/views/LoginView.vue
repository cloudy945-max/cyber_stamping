<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function onSubmit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    const redirect = (route.query.redirect as string) || '/timeline'
    router.replace(redirect)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '登录失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="brand">
        <div class="brand-icon">✦</div>
        <h1 class="brand-title">集章本</h1>
        <div class="brand-sub">个人电子印章打卡</div>
      </div>

      <form @submit.prevent="onSubmit" class="login-form">
        <label class="field">
          <span class="label">用户名</span>
          <input
            v-model="username"
            type="text"
            autocomplete="username"
            placeholder="请输入用户名"
            required
          />
        </label>

        <label class="field">
          <span class="label">密码</span>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            required
          />
        </label>

        <p v-if="error" class="error">{{ error }}</p>

        <button type="submit" :disabled="loading" class="submit">
          {{ loading ? '登录中…' : '进入集章本' }}
        </button>
      </form>

      <div class="foot">私人手账 · 仅本机使用</div>
    </div>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem 1rem;
  background:
    radial-gradient(circle at 30% 20%, rgba(255, 245, 220, 0.6), transparent 60%),
    radial-gradient(circle at 70% 80%, rgba(210, 180, 140, 0.25), transparent 55%),
    #f5e6c8;
}

.login-card {
  width: 100%;
  max-width: 360px;
  background: #fbf1dd;
  border: 1px solid #c9a877;
  border-radius: 10px;
  padding: 2rem 1.6rem 1.4rem;
  box-shadow: 0 6px 24px rgba(61, 40, 23, 0.12);
  position: relative;
}

.login-card::before {
  content: '';
  position: absolute;
  inset: 6px;
  border: 1px dashed #c9a877;
  border-radius: 7px;
  pointer-events: none;
  opacity: 0.5;
}

.brand {
  text-align: center;
  margin-bottom: 1.4rem;
}

.brand-icon {
  font-size: 1.8rem;
  color: #6b4423;
}

.brand-title {
  margin: 0.2rem 0 0;
  font-size: 1.5rem;
  color: #3d2817;
  letter-spacing: 0.15em;
}

.brand-sub {
  font-size: 0.85rem;
  color: #8b6f47;
  margin-top: 0.15rem;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.label {
  font-size: 0.85rem;
  color: #6b4423;
}

.error {
  margin: 0;
  color: #b04030;
  font-size: 0.85rem;
  text-align: center;
}

.submit {
  margin-top: 0.4rem;
  width: 100%;
}

.foot {
  margin-top: 1.1rem;
  text-align: center;
  font-size: 0.75rem;
  color: #a08560;
  letter-spacing: 0.1em;
}
</style>
