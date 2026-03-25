<template>
  <div class="my-page">
    <a-card>
      <a-tabs v-model:activeKey="activeTab">
        <a-tab-pane key="favorites" tab="收藏的政务文件">
          <a-list
            :data-source="favorites"
            :loading="loadingFavorites"
            :locale="{ emptyText: '暂无收藏' }"
          >
            <template #renderItem="{ item }">
              <a-list-item class="list-item">
                <div class="list-main">
                  <a class="doc-link" @click="goDetail(item.policy_id)">{{ item.title }}</a>
                  <div class="list-meta">
                    <span>{{ item.file_name || '未命名文件' }}</span>
                    <span>{{ formatDate(item.publish_date) }}</span>
                  </div>
                </div>
                <div class="list-stats">
                  <span><like-outlined /> {{ item.likes_count }}</span>
                  <span><star-outlined /> {{ item.follows_count }}</span>
                  <span><message-outlined /> {{ item.comments_count }}</span>
                </div>
              </a-list-item>
            </template>
          </a-list>
        </a-tab-pane>

        <a-tab-pane key="replies" tab="收到的评论回复">
          <a-list
            :data-source="replies"
            :loading="loadingReplies"
            :locale="{ emptyText: '暂无回复' }"
          >
            <template #renderItem="{ item }">
              <a-list-item class="list-item">
                <div class="list-main">
                  <div class="reply-header">
                    <span class="reply-user">{{ item.display_name || item.username }}</span>
                    <span class="reply-doc" @click="goDetail(item.policy_id)">
                      {{ item.policy_title }}
                    </span>
                  </div>
                  <div class="reply-content">
                    <div class="reply-parent">原评论：{{ item.parent_content }}</div>
                    <div class="reply-text">回复内容：{{ item.content }}</div>
                  </div>
                  <div class="list-meta">
                    <span>{{ formatDateTime(item.created_at) }}</span>
                  </div>
                </div>
              </a-list-item>
            </template>
          </a-list>
        </a-tab-pane>

        <a-tab-pane key="questions" :tab="questionTabTitle">
          <a-list
            :data-source="questions"
            :loading="loadingQuestions"
            :locale="{ emptyText: '暂无问题' }"
          >
            <template #renderItem="{ item }">
              <a-list-item class="list-item">
                <div class="list-main">
                  <div class="reply-header">
                    <span>{{ item.asked_by_display || item.asked_by || '公众' }}</span>
                    <span class="reply-doc" @click="goDetail(item.policy_id)">
                      {{ item.policy_title }}
                    </span>
                  </div>
                  <div class="reply-content">
                    <div class="reply-parent">问题：{{ item.content }}</div>
                  </div>
                  <div class="list-meta">
                    <span>{{ formatDateTime(item.created_at) }}</span>
                    <a-tag
                      v-if="item.moderation_status !== 'approved'"
                      :color="item.moderation_status === 'pending' ? 'orange' : 'red'"
                    >
                      {{ item.moderation_status === 'pending' ? '审核中' : '未通过' }}
                    </a-tag>
                  </div>
                  <div v-if="item.answers?.length" class="answer-list">
                    <div v-for="answer in item.answers" :key="answer.comment_id" class="answer-item">
                      <div class="reply-header">
                        <span>{{ answer.display_name || answer.username }}</span>
                      </div>
                      <div class="reply-text">答复：{{ answer.content }}</div>
                      <div class="list-meta">
                        <span>{{ formatDateTime(answer.created_at) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="list-actions">
                  <a-button size="small" @click="goDetail(item.policy_id)">前往详情</a-button>
                </div>
              </a-list-item>
            </template>
          </a-list>
        </a-tab-pane>

        <a-tab-pane key="activities" tab="我的操作记录">
          <a-list
            :data-source="activities"
            :loading="loadingActivities"
            :locale="{ emptyText: '暂无记录' }"
          >
            <template #renderItem="{ item }">
              <a-list-item class="list-item">
                <div class="list-main">
                  <div class="reply-header">
                    <span class="behavior-tag">{{ formatBehavior(item.behavior_type) }}</span>
                    <span
                      v-if="item.policy_id"
                      class="reply-doc"
                      @click="goDetail(item.policy_id)"
                    >
                      {{ item.policy_title || item.file_name || '未知文件' }}
                    </span>
                    <span v-else class="reply-doc muted">系统搜索</span>
                  </div>
                  <div class="list-meta">
                    <span>{{ formatDateTime(item.happened_at) }}</span>
                  </div>
                </div>
              </a-list-item>
            </template>
          </a-list>
        </a-tab-pane>
      </a-tabs>
    </a-card>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useStore } from 'vuex'
import { message } from 'ant-design-vue'
import { LikeOutlined, StarOutlined, MessageOutlined } from '@ant-design/icons-vue'
import api from '@/services/api'
import dayjs from 'dayjs'

export default {
  name: 'MyPage',
  components: {
    LikeOutlined,
    StarOutlined,
    MessageOutlined
  },
  setup() {
    const router = useRouter()
    const store = useStore()
    const activeTab = ref('favorites')
    const favorites = ref([])
    const replies = ref([])
    const questions = ref([])
    const activities = ref([])
    const loadingFavorites = ref(false)
    const loadingReplies = ref(false)
    const loadingQuestions = ref(false)
    const loadingActivities = ref(false)

    const roles = computed(() => store.getters['auth/roles'] || [])
    const staffRoles = ['staff', 'leader', 'admin']
    const isPublicOnly = computed(() => roles.value.includes('public') && !roles.value.some(r => staffRoles.includes(r)))
    const questionTabTitle = computed(() => (isPublicOnly.value ? '我的提问' : '公众问题'))

    const goDetail = (policyId) => {
      router.push(`/public-docs/${policyId}`)
    }

    const fetchFavorites = async () => {
      loadingFavorites.value = true
      try {
        const resp = await api.get('/public/docs/me/favorites')
        favorites.value = resp.items || []
      } catch (error) {
        message.error('获取收藏失败：' + error.message)
      } finally {
        loadingFavorites.value = false
      }
    }

    const fetchReplies = async () => {
      loadingReplies.value = true
      try {
        const resp = await api.get('/public/docs/me/replies')
        replies.value = resp.items || []
      } catch (error) {
        message.error('获取回复失败：' + error.message)
      } finally {
        loadingReplies.value = false
      }
    }

    const fetchQuestions = async () => {
      loadingQuestions.value = true
      try {
        const resp = await api.get('/public/docs/me/questions')
        questions.value = resp.items || []
      } catch (error) {
        message.error('获取问题失败：' + error.message)
      } finally {
        loadingQuestions.value = false
      }
    }

    const fetchActivities = async () => {
      loadingActivities.value = true
      try {
        const resp = await api.get('/public/docs/me/activities', {
          params: { limit: 100 }
        })
        activities.value = resp.items || []
      } catch (error) {
        message.error('获取操作记录失败：' + error.message)
      } finally {
        loadingActivities.value = false
      }
    }

    const formatBehavior = (value) => {
      const map = {
        click: '查看',
        search: '搜索',
        favorite: '收藏/关注',
        favorite_add: '收藏/关注',
        favorite_remove: '取消收藏/取消关注',
        comment: '评论/互动',
        download: '下载'
      }
      return map[value] || value || '-'
    }

    const formatDate = (value) => {
      return value ? dayjs(value).format('YYYY-MM-DD') : '-'
    }

    const formatDateTime = (value) => {
      return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
    }

    onMounted(() => {
      fetchFavorites()
      fetchReplies()
      fetchQuestions()
      fetchActivities()
    })

    return {
      activeTab,
      favorites,
      replies,
      questions,
      activities,
      loadingFavorites,
      loadingReplies,
      loadingQuestions,
      loadingActivities,
      questionTabTitle,
      goDetail,
      formatBehavior,
      formatDate,
      formatDateTime
    }
  }
}
</script>

<style lang="less" scoped>
.my-page {
  padding: 16px;
  background: #f5f5f5;
  min-height: 100%;
}

.list-item {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.list-main {
  flex: 1;
  min-width: 0;
}

.doc-link {
  font-size: 15px;
  font-weight: 600;
  color: #262626;
}

.doc-link:hover {
  color: #1677ff;
}

.list-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #8c8c8c;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.list-stats {
  display: flex;
  gap: 12px;
  color: #8c8c8c;
  font-size: 13px;
  align-items: center;
}

.reply-header {
  display: flex;
  gap: 8px;
  font-size: 13px;
  color: #595959;
  align-items: center;
}

.reply-doc {
  color: #1677ff;
  cursor: pointer;
}

.reply-doc.muted {
  color: #999;
  cursor: default;
}

.behavior-tag {
  display: inline-flex;
  padding: 2px 6px;
  background: #f0f5ff;
  color: #1d39c4;
  border-radius: 4px;
  font-size: 12px;
}

.reply-content {
  margin: 6px 0;
  color: #333;
}

.reply-parent,
.reply-text {
  line-height: 1.6;
}

.answer-list {
  margin-top: 8px;
  padding-left: 12px;
  border-left: 2px solid #f0f0f0;
}

.answer-item {
  padding: 4px 0;
}

.list-actions {
  display: flex;
  align-items: center;
}
</style>
