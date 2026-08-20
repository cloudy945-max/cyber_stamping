import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
  { path: '/', redirect: '/timeline' },
  { path: '/timeline', name: 'timeline', component: () => import('@/views/TimelineView.vue'), meta: { requiresAuth: true } },
  { path: '/map', name: 'map', component: () => import('@/views/MapView.vue'), meta: { requiresAuth: true } },
  { path: '/upload', name: 'upload', component: () => import('@/views/UploadView.vue'), meta: { requiresAuth: true } },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫：未登录访问受保护页面 → 跳登录
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.token) {
    return { name: 'timeline' }
  }
  return true
})
