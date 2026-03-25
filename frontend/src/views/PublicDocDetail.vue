<template>
  <div class="doc-detail">
    <div class="detail-header">
      <a-button type="link" @click="goBack">返回公开文件</a-button>
    </div>

    <a-card :loading="loadingDetail" class="detail-card">
      <div class="detail-title">
        <h2>{{ docDetail?.title || '公开文件详情' }}</h2>
        <a-tag color="blue" v-if="docDetail?.publish_date">
          {{ formatDate(docDetail.publish_date) }}
        </a-tag>
      </div>
      <div class="detail-meta">
        <span>文件名：{{ docDetail?.file_name || '未命名文件' }}</span>
        <span>发布单位：{{ docDetail?.publisher_org || '未填' }}</span>
        <span>状态：{{ docDetail?.status || '未知' }}</span>
      </div>
      <div class="detail-stats">
        <span><like-outlined /> {{ docDetail?.likes_count || 0 }}</span>
        <span><star-outlined /> {{ docDetail?.follows_count || 0 }}</span>
        <span><message-outlined /> {{ docDetail?.comments_count || 0 }}</span>
      </div>
      <div class="detail-actions">
        <a-space>
          <a-button type="text" @click="toggleLike">
            <template #icon>
              <like-filled v-if="docDetail?.user_liked" />
              <like-outlined v-else />
            </template>
            点赞
          </a-button>
          <a-button type="text" @click="toggleFollow">
            <template #icon>
              <star-filled v-if="docDetail?.user_followed" />
              <star-outlined v-else />
            </template>
            关注
          </a-button>
          <a-button type="primary" @click="askAboutDoc">
            <template #icon><question-circle-outlined /></template>
            针对提问
          </a-button>
        </a-space>
      </div>
    </a-card>

    <div class="detail-grid">
      <a-card title="评论区" class="panel-card">
        <div class="comment-input">
          <a-textarea
            v-model:value="commentInput"
            :rows="3"
            placeholder="请输入评论内容（将进行AI审核）"
          />
          <a-button
            type="primary"
            :loading="commentSubmitting"
            @click="submitComment"
          >
            发表评论
          </a-button>
        </div>

        <a-list
          :data-source="commentList"
          :locale="{ emptyText: '暂无评论' }"
          class="comment-list"
        >
          <template #renderItem="{ item }">
            <a-list-item class="comment-item">
              <div class="comment-main">
                <div class="comment-header">
                  <span>{{ item.display_name || item.username }}</span>
                  <a-tag
                    v-if="item.moderation_status !== 'approved'"
                    :color="item.moderation_status === 'pending' ? 'orange' : 'red'"
                  >
                    {{ item.moderation_status === 'pending' ? '审核中' : '未通过' }}
                  </a-tag>
                </div>
                <div class="comment-content">{{ item.content }}</div>
                <div class="comment-footer">
                  <span>{{ formatDateTime(item.created_at) }}</span>
                  <a-button type="link" size="small" @click="startReply(item.comment_id)">
                    回复
                  </a-button>
                </div>
              </div>

              <div v-if="item.replies?.length" class="comment-replies">
                <div v-for="reply in item.replies" :key="reply.comment_id" class="reply-item">
                  <div class="comment-header">
                    <span>{{ reply.display_name || reply.username }}</span>
                    <a-tag
                      v-if="reply.moderation_status !== 'approved'"
                      :color="reply.moderation_status === 'pending' ? 'orange' : 'red'"
                    >
                      {{ reply.moderation_status === 'pending' ? '审核中' : '未通过' }}
                    </a-tag>
                  </div>
                  <div class="comment-content">{{ reply.content }}</div>
                  <div class="comment-footer">
                    <span>{{ formatDateTime(reply.created_at) }}</span>
                  </div>
                </div>
              </div>

              <div v-if="replyingCommentId === item.comment_id" class="reply-input">
                <a-textarea
                  v-model:value="replyInput"
                  :rows="2"
                  placeholder="请输入回复内容"
                />
                <div class="reply-actions">
                  <a-button size="small" @click="cancelReply">取消</a-button>
                  <a-button
                    size="small"
                    type="primary"
                    :loading="replySubmitting"
                    @click="submitReply(item.comment_id)"
                  >
                    发送
                  </a-button>
                </div>
              </div>
            </a-list-item>
          </template>
        </a-list>
      </a-card>

      <a-card :title="qaTitle" class="panel-card">
        <div class="qa-input" v-if="canAskQuestion">
          <a-textarea
            v-model:value="questionInput"
            :rows="3"
            placeholder="请输入提问内容（将进行AI审核）"
          />
          <a-button
            type="primary"
            :loading="questionSubmitting"
            @click="submitQuestion"
          >
            提交问题
          </a-button>
        </div>
        <div class="qa-note" v-else>
          该区域用于集中回答公众提问。
        </div>

        <a-list
          :data-source="questionList"
          :locale="{ emptyText: '暂无问题' }"
          class="qa-list"
        >
          <template #renderItem="{ item }">
            <a-list-item class="qa-item">
              <div class="qa-question">
                <div class="comment-header">
                  <span>{{ item.display_name || item.username }}</span>
                  <a-tag
                    v-if="item.moderation_status !== 'approved'"
                    :color="item.moderation_status === 'pending' ? 'orange' : 'red'"
                  >
                    {{ item.moderation_status === 'pending' ? '审核中' : '未通过' }}
                  </a-tag>
                </div>
                <div class="comment-content">{{ item.content }}</div>
                <div class="comment-footer">
                  <span>{{ formatDateTime(item.created_at) }}</span>
                  <a-button
                    v-if="canAnswerQuestion"
                    type="link"
                    size="small"
                    @click="startAnswer(item.comment_id)"
                  >
                    回答
                  </a-button>
                </div>
              </div>

              <div v-if="item.answers?.length" class="qa-answers">
                <div v-for="answer in item.answers" :key="answer.comment_id" class="answer-item">
                  <div class="comment-header">
                    <span>{{ answer.display_name || answer.username }}</span>
                    <a-tag
                      v-if="answer.moderation_status !== 'approved'"
                      :color="answer.moderation_status === 'pending' ? 'orange' : 'red'"
                    >
                      {{ answer.moderation_status === 'pending' ? '审核中' : '未通过' }}
                    </a-tag>
                  </div>
                  <div class="comment-content">{{ answer.content }}</div>
                  <div class="comment-footer">
                    <span>{{ formatDateTime(answer.created_at) }}</span>
                  </div>
                </div>
              </div>

              <div v-if="answeringQuestionId === item.comment_id" class="answer-input">
                <a-textarea
                  v-model:value="answerInput"
                  :rows="2"
                  placeholder="请输入答复内容"
                />
                <div class="reply-actions">
                  <a-button size="small" @click="cancelAnswer">取消</a-button>
                  <a-button
                    size="small"
                    type="primary"
                    :loading="answerSubmitting"
                    @click="submitAnswer(item.comment_id)"
                  >
                    发送答复
                  </a-button>
                </div>
              </div>
            </a-list-item>
          </template>
        </a-list>
      </a-card>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStore } from 'vuex'
import { message } from 'ant-design-vue'
import {
  LikeOutlined,
  LikeFilled,
  StarOutlined,
  StarFilled,
  MessageOutlined,
  QuestionCircleOutlined
} from '@ant-design/icons-vue'
import api from '@/services/api'
import dayjs from 'dayjs'

export default {
  name: 'PublicDocDetail',
  components: {
    LikeOutlined,
    LikeFilled,
    StarOutlined,
    StarFilled,
    MessageOutlined,
    QuestionCircleOutlined
  },
  setup() {
    const route = useRoute()
    const router = useRouter()
    const store = useStore()
    const policyId = computed(() => route.params.policyId)
    const loadingDetail = ref(false)
    const docDetail = ref(null)
    const commentList = ref([])
    const commentInput = ref('')
    const commentSubmitting = ref(false)
    const replyInput = ref('')
    const replyingCommentId = ref(null)
    const replySubmitting = ref(false)

    const questionList = ref([])
    const questionInput = ref('')
    const questionSubmitting = ref(false)
    const answerInput = ref('')
    const answeringQuestionId = ref(null)
    const answerSubmitting = ref(false)

    const roles = computed(() => store.getters['auth/roles'] || [])
    const staffRoles = ['staff', 'leader', 'admin']
    const isPublicOnly = computed(() => roles.value.includes('public') && !roles.value.some(r => staffRoles.includes(r)))
    const isLeader = computed(() => roles.value.includes('leader'))
    const isStaff = computed(() => roles.value.includes('staff'))
    const isAdmin = computed(() => roles.value.includes('admin'))
    const canAskQuestion = computed(() => isPublicOnly.value)
    const canAnswerQuestion = computed(() => roles.value.some(r => staffRoles.includes(r)))
    const qaTitle = computed(() => {
      if (canAskQuestion.value) return '提问政府'
      if (isLeader.value) return '领导答复'
      if (isStaff.value || isAdmin.value) return '回答公众'
      return '回答公众'
    })

    const fetchDetail = async () => {
      loadingDetail.value = true
      try {
        docDetail.value = await api.get(`/public/docs/${policyId.value}`)
      } catch (error) {
        message.error('获取文件详情失败：' + error.message)
      } finally {
        loadingDetail.value = false
      }
    }

    const fetchComments = async () => {
      try {
        const resp = await api.get(`/public/docs/${policyId.value}/comments`, {
          params: { include_mine: true }
        })
        commentList.value = resp.items || []
      } catch (error) {
        message.error('获取评论失败：' + error.message)
      }
    }

    const fetchQuestions = async () => {
      try {
        const resp = await api.get(`/public/docs/${policyId.value}/questions`, {
          params: { include_mine: true }
        })
        questionList.value = resp.items || []
      } catch (error) {
        message.error('获取问题失败：' + error.message)
      }
    }

    const toggleLike = async () => {
      if (!docDetail.value) return
      try {
        const url = `/public/docs/${docDetail.value.policy_id}/like`
        const resp = docDetail.value.user_liked ? await api.delete(url) : await api.post(url)
        docDetail.value.user_liked = !docDetail.value.user_liked
        docDetail.value.likes_count = resp.likes_count ?? docDetail.value.likes_count
      } catch (error) {
        message.error('操作失败：' + error.message)
      }
    }

    const toggleFollow = async () => {
      if (!docDetail.value) return
      try {
        const url = `/public/docs/${docDetail.value.policy_id}/follow`
        const resp = docDetail.value.user_followed ? await api.delete(url) : await api.post(url)
        docDetail.value.user_followed = !docDetail.value.user_followed
        docDetail.value.follows_count = resp.follows_count ?? docDetail.value.follows_count
      } catch (error) {
        message.error('操作失败：' + error.message)
      }
    }

    const submitComment = async () => {
      if (!commentInput.value.trim()) {
        message.warning('请输入评论内容')
        return
      }
      commentSubmitting.value = true
      try {
        await api.post(`/public/docs/${policyId.value}/comments`, {
          content: commentInput.value.trim()
        })
        commentInput.value = ''
        message.success('评论已提交，等待审核')
        fetchComments()
      } catch (error) {
        message.error('评论提交失败：' + error.message)
      } finally {
        commentSubmitting.value = false
      }
    }

    const startReply = (commentId) => {
      replyingCommentId.value = commentId
      replyInput.value = ''
    }

    const cancelReply = () => {
      replyingCommentId.value = null
      replyInput.value = ''
    }

    const submitReply = async (commentId) => {
      if (!replyInput.value.trim()) {
        message.warning('请输入回复内容')
        return
      }
      replySubmitting.value = true
      try {
        await api.post(`/public/docs/${policyId.value}/comments`, {
          content: replyInput.value.trim(),
          parent_comment_id: commentId
        })
        replyInput.value = ''
        replyingCommentId.value = null
        message.success('回复已提交，等待审核')
        fetchComments()
      } catch (error) {
        message.error('回复提交失败：' + error.message)
      } finally {
        replySubmitting.value = false
      }
    }

    const submitQuestion = async () => {
      if (!questionInput.value.trim()) {
        message.warning('请输入问题内容')
        return
      }
      questionSubmitting.value = true
      try {
        await api.post(`/public/docs/${policyId.value}/questions`, {
          content: questionInput.value.trim()
        })
        questionInput.value = ''
        message.success('问题已提交，等待审核')
        fetchQuestions()
      } catch (error) {
        message.error('问题提交失败：' + error.message)
      } finally {
        questionSubmitting.value = false
      }
    }

    const startAnswer = (questionId) => {
      answeringQuestionId.value = questionId
      answerInput.value = ''
    }

    const cancelAnswer = () => {
      answeringQuestionId.value = null
      answerInput.value = ''
    }

    const submitAnswer = async (questionId) => {
      if (!answerInput.value.trim()) {
        message.warning('请输入答复内容')
        return
      }
      answerSubmitting.value = true
      try {
        await api.post(`/public/docs/${policyId.value}/questions/${questionId}/answers`, {
          content: answerInput.value.trim()
        })
        answerInput.value = ''
        answeringQuestionId.value = null
        message.success('答复已提交，等待审核')
        fetchQuestions()
      } catch (error) {
        message.error('答复提交失败：' + error.message)
      } finally {
        answerSubmitting.value = false
      }
    }

    const askAboutDoc = () => {
      const docId = docDetail.value?.doc_ids?.[0]
      if (!docId) {
        message.warning('该文件尚未建立文档索引')
        return
      }
      router.push({
        path: '/chat',
        query: {
          doc_id: docId,
          doc_name: docDetail.value?.title || docDetail.value?.file_name || ''
        }
      })
    }

    const goBack = () => {
      router.push('/public-docs')
    }

    const formatDate = (value) => {
      return value ? dayjs(value).format('YYYY-MM-DD') : '-'
    }

    const formatDateTime = (value) => {
      return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
    }

    const refreshAll = () => {
      fetchDetail()
      fetchComments()
      fetchQuestions()
    }

    onMounted(refreshAll)
    watch(policyId, () => {
      refreshAll()
    })

    return {
      loadingDetail,
      docDetail,
      commentList,
      commentInput,
      commentSubmitting,
      replyInput,
      replyingCommentId,
      replySubmitting,
      questionList,
      questionInput,
      questionSubmitting,
      answerInput,
      answeringQuestionId,
      answerSubmitting,
      canAskQuestion,
      canAnswerQuestion,
      qaTitle,
      toggleLike,
      toggleFollow,
      submitComment,
      startReply,
      cancelReply,
      submitReply,
      submitQuestion,
      startAnswer,
      cancelAnswer,
      submitAnswer,
      askAboutDoc,
      goBack,
      formatDate,
      formatDateTime
    }
  }
}
</script>

<style lang="less" scoped>
.doc-detail {
  padding: 16px;
  background: #f5f5f5;
  min-height: 100%;
}

.detail-header {
  margin-bottom: 8px;
}

.detail-card {
  margin-bottom: 16px;
}

.detail-title {
  display: flex;
  align-items: center;
  gap: 12px;

  h2 {
    margin: 0;
    font-size: 20px;
  }
}

.detail-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: #666;
  font-size: 13px;
}

.detail-stats {
  margin-top: 8px;
  display: flex;
  gap: 16px;
  color: #8c8c8c;
}

.detail-actions {
  margin-top: 12px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.panel-card {
  height: 100%;
}

.comment-input,
.qa-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.qa-note {
  margin-bottom: 16px;
  font-size: 13px;
  color: #999;
}

.comment-list,
.qa-list {
  max-height: 520px;
  overflow: auto;
}

.comment-item,
.qa-item {
  padding: 8px 0;
}

.comment-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #595959;
}

.comment-content {
  margin: 6px 0;
  color: #333;
  line-height: 1.6;
}

.comment-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #999;
  font-size: 12px;
}

.comment-replies,
.qa-answers {
  margin-top: 8px;
  padding-left: 16px;
  border-left: 2px solid #f0f0f0;
}

.reply-item,
.answer-item {
  padding: 6px 0;
}

.reply-input,
.answer-input {
  margin-top: 8px;
  padding: 8px;
  background: #fafafa;
  border-radius: 6px;
}

.reply-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}
</style>
