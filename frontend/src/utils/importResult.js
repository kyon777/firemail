export function getImportResultFeedback(result) {
  const success = Number(result?.success || 0)
  const failed = Number(result?.failed || 0)

  return {
    type: success > 0 && failed === 0 ? 'success' : 'warning',
    message: `批量导入完成：成功 ${success} 个，失败 ${failed} 个`
  }
}
