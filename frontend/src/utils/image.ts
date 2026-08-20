/** 印章图片 URL 工具：拼接 access_token 到 query 参数。

 * 背景：<img src="..."> 标签由浏览器原生发起请求，无法注入 axios 拦截器的
 * Authorization header，会导致需要登录的 image 接口 401。
 * 解决：后端 get_current_user 同时支持 ?access_token=<token>，
 * 前端用本工具拼接 token 到 URL query，浏览器即可正常加载图片。
 *
 * token 来源：localStorage（与 stores/auth.ts 的 TOKEN_KEY 一致），
 * 避免在工具函数中引入 pinia store 造成循环依赖。
 */
const TOKEN_KEY = 'cyber_stamping_token'

/** 拼接印章图片 URL，自动带上 access_token query 参数。
 * @param id 印章 id
 * @param variant original / sticker
 */
export function stampImageUrl(
  id: number,
  variant: 'original' | 'sticker' = 'original',
): string {
  const token = localStorage.getItem(TOKEN_KEY) || ''
  const q = new URLSearchParams({
    variant,
    access_token: token,
  })
  return `/api/stamps/${id}/image?${q.toString()}`
}
