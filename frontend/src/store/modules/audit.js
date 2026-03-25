import { chatAPI, governmentAPI } from '../../services/api'
import JSON5 from 'json5'

export default {
  namespaced: true,
  state: {
    // 审计报告列表
    reports: [],
    // 当前报告
    currentReport: null,
    // 审计状态
    auditStatus: 'idle', // idle, auditing, completed, failed
    // 审计配置
    auditConfig: {
      auditType: 'compliance', // compliance, completeness, consistency, accuracy, security
      targetQuery: '',
      auditRules: [],
      includeRecommendations: true,
      detailedAnalysis: true
    }
  },
  mutations: {
    // 设置报告列表
    SET_REPORTS(state, reports) {
      state.reports = reports
    },
    // 添加报告
    ADD_REPORT(state, report) {
      state.reports.unshift(report)
    },
    // 设置当前报告
    SET_CURRENT_REPORT(state, report) {
      state.currentReport = report
    },
    // 更新报告
    UPDATE_REPORT(state, { reportId, updates }) {
      const index = state.reports.findIndex(r => r.id === reportId)
      if (index !== -1) {
        state.reports[index] = { ...state.reports[index], ...updates }
      }
      if (state.currentReport && state.currentReport.id === reportId) {
        state.currentReport = { ...state.currentReport, ...updates }
      }
    },
    // 删除报告
    REMOVE_REPORT(state, reportId) {
      state.reports = state.reports.filter(r => r.id !== reportId)
      if (state.currentReport && state.currentReport.id === reportId) {
        state.currentReport = null
      }
    },
    // 设置审计状态
    SET_AUDIT_STATUS(state, status) {
      state.auditStatus = status
    },
    // 设置审计配置
    SET_AUDIT_CONFIG(state, config) {
      state.auditConfig = { ...state.auditConfig, ...config }
    },
    // 重置审计配置
    RESET_AUDIT_CONFIG(state) {
      state.auditConfig = {
        auditType: 'compliance',
        targetQuery: '',
        auditRules: [],
        includeRecommendations: true,
        detailedAnalysis: true
      }
    }
  },
  actions: {
    // 执行审计
    async conductAudit({ commit }, config) {
      try {
        commit('SET_AUDIT_STATUS', 'auditing')
        commit('SET_AUDIT_CONFIG', config)
        
        // 使用聊天接口生成审计报告（JSON 输出）
        const escapeBraces = (s) => s?.replace(/\{/g, '{{').replace(/\}/g, '}}') || ''

        // 针对活动评估与通用审计两种提示
        const isActivityAudit = Boolean(config.activityDescription)

        const typeLabelMap = {
          compliance: '合规性',
          completeness: '完整性',
          consistency: '一致性',
          accuracy: '准确性',
          security: '安全性',
          activity: '活动评估'
        }
        const typeLabel = typeLabelMap[config.auditType] || (isActivityAudit ? '活动评估' : (config.auditType || '审计'))

        const systemPromptRaw = isActivityAudit
          ? [
              '你是一名政务活动审计专家。',
              '根据用户提供的活动名称与描述，从已入库文档中检索证据并输出结构化的审计评估报告。',
              '严格只返回 JSON，不要包含任何多余文本或 Markdown。',
              'JSON 结构如下：',
              '{',
              '  "reportId": string,',
              '  "activityName": string,',
              '  "summary": string,',
              '  "overallCompleted": boolean,',
              '  "overallScore": number,',
              '  "totalDocumentsReviewed": number,',
              '  "indicatorResults": [{',
              '      "name": string,',
              '      "target": string|number|null,',
              '      "actual": string|number|null,',
              '      "unit": string|null,',
              '      "status": string,',
              '      "score": number,',
              '      "evidence"?: string,',
              '      "notes"?: string',
              '  }],',
              '  "recommendationsSummary": string[]',
              '}',
              '所有字段必须存在，缺失时给出合理的空值（如 false、0、[]、""）。',
              '中文输出。'
            ].join('\n')
          : [
              '你是一名政务文档审计专家。',
              '根据用户的审计目标，从已入库文档中检索证据并输出结构化的审计报告。',
              '严格只返回 JSON，不要包含任何多余文本或 Markdown。',
              'JSON 结构如下：',
              '{',
              '  "auditType": string,',
              '  "summary": string,',
              '  "complianceScore": number,',
              '  "totalDocumentsReviewed": number,',
              '  "issuesBySeverity": { "critical"?: number, "high"?: number, "medium"?: number, "low"?: number },',
              '  "findings": [{',
              '      "title": string,',
              '      "severity": "critical"|"high"|"medium"|"low",',
              '      "description": string,',
              '      "evidence"?: string,',
              '      "impactAssessment"?: string,',
              '      "recommendations"?: string[],',
              '      "sources"?: any[]',
              '  }],',
              '  "recommendationsSummary": string[]',
              '}',
              '所有字段必须存在，缺失时给出合理的空值（如 0、[]、""）。',
              '中文输出。'
            ].join('\n')
        const systemPrompt = escapeBraces(systemPromptRaw)

        const userPromptRaw = isActivityAudit
          ? [
              `审计类型: ${typeLabel}`,
              `活动名称: ${config.activityName || ''}`,
              `活动描述: ${config.activityDescription || ''}`,
              config.includeRecommendations ? '需要提供改进建议。' : '不必提供改进建议。',
              config.detailedAnalysis ? '需要详细分析与证据。' : '只需提供要点摘要。'
            ].join('\n')
          : [
              `审计类型: ${typeLabel}`,
              `审计目标: ${config.targetQuery || ''}`,
              config.includeRecommendations ? '需要提供改进建议。' : '不必提供改进建议。',
              config.detailedAnalysis ? '需要详细分析与证据。' : '只需提供要点摘要。'
            ].join('\n')
        const userPrompt = escapeBraces(userPromptRaw)

        const resp = await chatAPI.completions([
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt }
        ], {
          useContext: true,
          contextFilter: config.contextFilter,
          includeSources: true,
          stream: false
        })

        const raw = resp?.choices?.[0]?.message?.content || ''

        // 尝试从文本中稳健地提取/修复 JSON
        const extractJson = (text) => {
          if (!text || typeof text !== 'string') return null
          // 去掉代码块围栏
          let t = text.replace(/^```json\s*|^```\s*|```\s*$/gmi, '').trim()
          // 替换智能引号
          t = t.replace(/[“”]/g, '"').replace(/[‘’]/g, "'")
          // 去掉无意义的零宽字符
          t = t.replace(/[\u200B-\u200D\uFEFF]/g, '')

          // 直接尝试解析
          try { return JSON.parse(t) } catch (_) { /* ignore parse error */ }
          try { return JSON5.parse(t) } catch (_) { /* ignore parse error */ }

          // 选择更可能是有效 JSON 的起点：优先以包含关键字段的位置为基准回溯到最近的 "{"，避免匹配到提示里的 {{
          const keyIdx = (() => {
            const k1 = t.indexOf('"reportId"')
            const k2 = t.indexOf('"auditType"')
            const k = [k1, k2].filter(i => i !== -1).sort((a,b) => a - b)[0]
            return (typeof k === 'number') ? k : -1
          })()
          const start = keyIdx !== -1 ? t.lastIndexOf('{', keyIdx) : t.indexOf('{')
          if (start !== -1) {
            let body = t.slice(start)

            // 如果末尾存在未结束的引号，截断到最后一个完整引号位置
            const endsWithOddQuotes = (s) => {
              let inStr = false
              let q = ''
              let escaped = false
              for (let i = 0; i < s.length; i++) {
                const c = s[i]
                if (escaped) { escaped = false; continue }
                if (c === '\\') { escaped = true; continue }
                if (inStr) {
                  if (c === q) inStr = false
                } else if (c === '"' || c === "'") {
                  inStr = true; q = c
                }
              }
              return inStr
            }
            if (endsWithOddQuotes(body)) {
              // 删除末尾未闭合的字符串片段
              const lastQuote = Math.max(body.lastIndexOf('"'), body.lastIndexOf("'"))
              if (lastQuote > -1) body = body.slice(0, lastQuote)
            }

            // 去掉末尾到行尾可能的半截键值/逗号
            body = body.replace(/[\s,]*$/, '')
            // 去掉尾部明显的非 JSON 噪声（例如日志中的 **** 分隔线等）
            body = body.replace(/[\r\n]*[*\-=_#\s]+$/g, '')
            // 尝试移除末尾残缺的 key 或 key:
            for (let i = 0; i < 2; i++) {
              // 逗号后跟着未闭合的 key
              body = body.replace(/,\s*"[^"\n]*$/m, '')
              // 末尾是完整的 "key": 但没有值
              body = body.replace(/"[^"\n]*"\s*:\s*$/m, '')
            }

            // 统计配对情况
            const stack = []
            let inString = false
            let quote = ''
            let escape = false
            for (let i = 0; i < body.length; i++) {
              const ch = body[i]
              if (escape) { escape = false; continue }
              if (ch === '\\') { escape = true; continue }
              if (inString) {
                if (ch === quote) inString = false
                continue
              }
              if (ch === '"' || ch === "'") { inString = true; quote = ch; continue }
              if (ch === '{' || ch === '[') stack.push(ch)
              else if (ch === '}' || ch === ']') stack.pop()
            }

            // 移除数组/对象中可能存在的尾随逗号
            body = body.replace(/,\s*(\]|\})/g, '$1')

            // 如果存在未闭合的结构，尝试补全
            if (stack.length > 0) {
              // 若末尾是逗号，先去掉
              body = body.replace(/,\s*$/g, '')
              for (let i = stack.length - 1; i >= 0; i--) {
                body += (stack[i] === '{') ? '}' : ']'
              }
            }

            // 再次移除因补全导致的尾随逗号以及尾部噪声
            body = body.replace(/,\s*(\]|\})/g, '$1')
            body = body.replace(/[\r\n]*[*\-=_#\s]+$/g, '')

            // 先尝试直接解析/宽松解析
            try { return JSON.parse(body) } catch (_) { /* ignore parse error */ }
            try { return JSON5.parse(body) } catch (_) { /* ignore parse error */ }

            // 逐步回退到上一个闭合的大括号位置，尝试解析（丢弃尾部不完整片段）
            let end = body.lastIndexOf('}')
            while (end !== -1) {
              let candidate = body.slice(0, end + 1)
              candidate = candidate.replace(/,\s*(\]|\})/g, '$1')
              try { return JSON.parse(candidate) } catch (_) { /* ignore parse error */ }
              try { return JSON5.parse(candidate) } catch (_) { /* ignore parse error */ }
              end = body.lastIndexOf('}', end - 1)
            }
          }

          return null
        }

        const parsed = extractJson(raw)

        if (!parsed) {
          if (process && process.env && process.env.NODE_ENV !== 'production') {
            // eslint-disable-next-line no-console
            console.debug('[audit] 原始响应无法解析为 JSON，前 500 字符：', (raw || '').slice(0, 500))
          }
          throw new Error('LLM 未返回有效审计报告')
        }

        // 兼容两种结构并映射到前端所需字段
        const toIndicator = (f) => ({
          name: f.name || f.title || '指标',
          target: f.target ?? '',
          actual: f.actual ?? (f.description || ''),
          unit: f.unit ?? '',
          status: f.status || f.severity || '未评估',
          score: Number(f.score ?? 0),
          evidence: f.evidence || '',
          notes: f.notes || ''
        })

        const indicatorResults = Array.isArray(parsed.indicatorResults)
          ? parsed.indicatorResults.map(toIndicator)
          : Array.isArray(parsed.findings)
            ? parsed.findings.map(toIndicator)
            : []

        const overallScore = Number(
          parsed.overallScore ?? parsed.complianceScore ?? 0
        )

        const report = {
          id: Date.now(),
          reportId: String(parsed.reportId || Date.now()),
          activityName: config.activityName || parsed.activityName || '',
          auditType: parsed.auditType || config.auditType || (isActivityAudit ? 'activity' : 'general'),
          summary: parsed.summary || '',
          overallCompleted: Boolean(
            typeof parsed.overallCompleted === 'boolean'
              ? parsed.overallCompleted
              : (indicatorResults.length > 0
                  ? indicatorResults.every(i => String(i.status || '').includes('完成') || String(i.status || '').toLowerCase().includes('pass'))
                  : overallScore >= 60)
          ),
          overallScore,
          totalDocumentsReviewed: Number(parsed.totalDocumentsReviewed ?? 0),
          indicatorResults,
          recommendationsSummary: Array.isArray(parsed.recommendationsSummary) ? parsed.recommendationsSummary : [],
          // 兼容旧字段，供其他视图/导出使用
          complianceScore: overallScore,
          findings: indicatorResults.map(i => ({
            title: i.name,
            severity: i.status,
            description: i.actual || '',
            evidence: i.evidence || '',
            recommendations: [],
          })),
          generatedAt: new Date().toISOString()
        }
        
        commit('ADD_REPORT', report)
        commit('SET_CURRENT_REPORT', report)
        commit('SET_AUDIT_STATUS', 'completed')
        
        return report
      } catch (error) {
        console.error('审计执行失败:', error)
        commit('SET_AUDIT_STATUS', 'failed')
        throw error
      }
    },
    
    // 获取审计报告列表
    async fetchReports({ commit }) {
      try {
        // TODO: 调用API获取报告列表
        const reports = []
        commit('SET_REPORTS', reports)
        return reports
      } catch (error) {
        console.error('获取报告列表失败:', error)
        throw error
      }
    },
    
    // 获取审计规则
    async fetchAuditRules() {
      try {
        const result = await governmentAPI.getAuditRules()
        return result.data
      } catch (error) {
        console.error('获取审计规则失败:', error)
        throw error
      }
    },
    
    // 保存报告
    async saveReport({ commit }, reportData) {
      try {
        // TODO: 调用API保存报告
        // const result = await saveReportAPI(reportData)
        
        const report = {
          ...reportData,
          id: reportData.id || Date.now(),
          savedAt: new Date().toISOString()
        }
        
        if (reportData.id) {
          commit('UPDATE_REPORT', { reportId: reportData.id, updates: report })
        } else {
          commit('ADD_REPORT', report)
        }
        
        return report
      } catch (error) {
        console.error('保存报告失败:', error)
        throw error
      }
    },
    
    // 删除报告
    async deleteReport({ commit }, reportId) {
      try {
        // TODO: 调用API删除报告
        // await deleteReportAPI(reportId)
        
        commit('REMOVE_REPORT', reportId)
      } catch (error) {
        console.error('删除报告失败:', error)
        throw error
      }
    },
    
    // 导出报告
    async exportReport({ state }, { reportId, format = 'pdf' }) {
      try {
        const report = state.reports.find(r => r.id === reportId) || state.currentReport
        if (!report) {
          throw new Error('未找到要导出的报告')
        }

        if (format === 'pdf') {
          const html = `<!DOCTYPE html><html><head><meta charset="utf-8"/>
          <title>审计报告</title>
          <style>
            body{font-family: Arial, Helvetica, sans-serif;padding:16px;}
            h1{font-size:18px;margin:0 0 12px 0}
            h2{font-size:16px;margin:16px 0 8px 0}
            table{border-collapse:collapse;width:100%;}
            th,td{border:1px solid #999;padding:6px 8px;font-size:12px;}
            th{background:#f5f5f5;text-align:left}
            .meta{margin-bottom:12px;color:#555}
          </style></head><body>
          <h1>${report.auditType}审计报告</h1>
          <div class="meta">生成时间：${report.generatedAt}</div>
          <h2>审计摘要</h2>
          <p>${report.summary || ''}</p>
          <h2>关键指标</h2>
          <table><tbody>
            <tr><th>合规评分</th><td>${report.complianceScore}</td></tr>
            <tr><th>审查文档</th><td>${report.totalDocumentsReviewed}</td></tr>
          </tbody></table>
          <h2>发现的问题（${report.findings.length}）</h2>
          ${report.findings.map(f => `<h3>${f.title}（${f.severity}）</h3>
            <p>${f.description || ''}</p>
            ${f.evidence ? `<p><strong>证据：</strong>${f.evidence}</p>` : ''}
            ${f.impactAssessment ? `<p><strong>影响评估：</strong>${f.impactAssessment}</p>` : ''}
            ${Array.isArray(f.recommendations) && f.recommendations.length ? `<p><strong>建议：</strong>${f.recommendations.join('；')}</p>` : ''}
          `).join('')}
          <h2>主要建议</h2>
          <p>${(report.recommendationsSummary || []).join('；')}</p>
          <script>window.onload=function(){window.print(); setTimeout(()=>window.close(),300);};</script>
          </body></html>`
          const w = window.open('', '_blank')
          if (!w) throw new Error('浏览器阻止了弹窗，请允许弹窗后重试')
          w.document.open(); w.document.write(html); w.document.close()
          return true
        }
        return false
      } catch (error) {
        console.error('导出报告失败:', error)
        throw error
      }
    },
    
    // 设置当前报告
    setCurrentReport({ commit }, report) {
      commit('SET_CURRENT_REPORT', report)
    },
    
    // 清空当前报告
    clearCurrentReport({ commit }) {
      commit('SET_CURRENT_REPORT', null)
      commit('SET_AUDIT_STATUS', 'idle')
    },
    
    // 重置配置
    resetConfig({ commit }) {
      commit('RESET_AUDIT_CONFIG')
      commit('SET_AUDIT_STATUS', 'idle')
    }
  },
  getters: {
    // 是否正在审计
    isAuditing: (state) => {
      return state.auditStatus === 'auditing'
    },
    
    // 审计是否完成
    isCompleted: (state) => {
      return state.auditStatus === 'completed'
    },
    
    // 审计是否失败
    isFailed: (state) => {
      return state.auditStatus === 'failed'
    },
    
    // 报告统计
    reportStats: (state) => {
      const total = state.reports.length
      const avgScore = state.reports.length > 0 
        ? state.reports.reduce((sum, r) => sum + r.complianceScore, 0) / state.reports.length
        : 0
      
      return {
        total,
        avgScore: Math.round(avgScore * 10) / 10
      }
    }
  }
}