<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Cpu, TrendCharts, Money, ShoppingCart, DataAnalysis, Setting, ZoomIn, ArrowLeft, ArrowRight, Tools } from '@element-plus/icons-vue'
import { ref, computed } from 'vue'
import mainViewImage from '@/assets/landing-page-mainView.png'
import githubIconWhite from '@/assets/github-mark-white.svg'
import aifadianLogo from '@/assets/横版-黑底-透明背景.png'
import industryPlanImage from '@/assets/landing-page-工业规划.png'
import marketAnalysisImage from '@/assets/landing-page-市场与利润分析.png'
import costCalculationImage from '@/assets/landing-page-成本计算.png'
import procurementListImage from '@/assets/landing-page-采购清单.png'
import assetManagementImage1 from '@/assets/landing-page-资产管理1.png'
import assetManagementImage2 from '@/assets/landing-page-资产管理2.png'
import assetManagementImage3 from '@/assets/landing-page-资产管理3.png'
import cooperativeProductionImage from '@/assets/landing-page-合作生产.png'
import oreRefiningImage from '@/assets/landing-page-化矿计算.png'

const router = useRouter()
const authStore = useAuthStore()

// GitHub 仓库地址
const GITHUB_REPO_URL = 'https://github.com/AraragiEro/EveKahunaSystem.git'

// 打开 GitHub 仓库
const openGitHub = () => {
  window.open(GITHUB_REPO_URL, '_blank')
}

// 捐赠链接（从环境变量读取）
const donateLink = computed(() => import.meta.env.VITE_DONATE_LINK as string | undefined)
const showDonateButton = computed(() => !!donateLink.value)

// 社交群号
const QQGroupNumber = computed(() => import.meta.env.VITE_QQ_GROUP as string | undefined)
const showQQGroupButton = computed(() => !!QQGroupNumber.value)

// 打开捐赠链接
const openDonate = () => {
  if (donateLink.value) {
    window.open(donateLink.value, '_blank')
  }
}

// 图片预览状态
const previewVisible = ref(false)
const previewImageList = ref<string[]>([])
const previewInitialIndex = ref(0)

// 打开图片预览
const openPreview = (images: string | string[], index: number = 0) => {
  if (Array.isArray(images)) {
    previewImageList.value = images
  } else {
    previewImageList.value = [images]
  }
  previewInitialIndex.value = index
  previewVisible.value = true
}

// 跳转到登录页
const goToLogin = () => {
  router.push('/login')
}

// 如果已登录，跳转到主页
const goToHome = () => {
  if (authStore.isAuthenticated) {
    router.push('/home')
  } else {
    router.push('/login')
  }
}

// 核心功能列表
const features = [
  {
    icon: Cpu,
    title: '工业规划',
    description: '智能工业制造规划与报表输出，支持计划分解树、材料清单、工作流等详细数据',
    color: '#409eff',
    image: industryPlanImage
  },
  {
    icon: TrendCharts,
    title: '市场与利润分析',
    description: '实时市场价格查询、自选清单价格监控、利润计算与深度分析，帮助您发现市场机会并做出最佳决策',
    color: '#67c23a',
    image: marketAnalysisImage
  },
  {
    icon: Money,
    title: '成本计算',
    description: '精确计算制造和采购成本，提供详略得当的成本报表，让您心中有数',
    color: '#e6a23c',
    image: costCalculationImage
  },
  {
    icon: ShoppingCart,
    title: '采购清单',
    description: '支持可复制的采购清单导出',
    color: '#f56c6c',
    image: procurementListImage
  },
  {
    icon: Setting,
    title: '资产管理',
    description: '角色和公司资产统计与管理，全面掌握您的资产状况，对库存状况了如指掌',
    color: '#606266',
    images: [assetManagementImage1, assetManagementImage2, assetManagementImage3]
  },
  {
    icon: DataAnalysis,
    title: '合作生产',
    description: '支持多角色协作生产，优化资源配置，提高生产效率',
    color: '#909399',
    image: cooperativeProductionImage
  },
  {
    icon: Tools,
    title: '化矿解算',
    description: '智能矿石精炼计算，帮助您优化化矿方案，最大化资源利用效率',
    color: '#9c27b0',
    image: oreRefiningImage
  }
]

// 系统特色
const highlights = [
  {
    title: '易理解',
    description: '通过简单易懂的方式回答"我该搓什么"、"搓出来赚钱吗"、"我该怎么搓"等核心问题'
  },
  {
    title: '可操作',
    description: '提供可参考可执行的工作流建议和物流建议，照着搬运和进行工作即可'
  },
  {
    title: '降低门槛',
    description: '为熟练度不足或希望节省精力的玩家提供一整套易理解、可操作的执行方案'
  }
]

// 定价方案
const pricingPlans = [
  {
    name: '免费用户',
    price: '免费',
    priceUnit: '',
    color: '#909399',
    features: [
      {
        category: '完整的工业流程计算相关功能',
        items: [
          '完整的计划功能',
          '除esi库存读取外的计划配置功能',
          '报表解锁',
          '  • 流程视图：详细的蓝图分解',
          '  • 材料视图：原材料的缺失情况',
          '  • 工作流：可执行的工作方案',
          '  • 采购视图：可进行一键采购的清单'
        ]
      }
    ],
    isPopular: false
  },
  {
    name: 'Alpha订阅',
    price: '500M',
    priceUnit: 'Isk/月',
    color: '#409eff',
    note: '注意：需要有总监权限才可以添加公司库存',
    features: [
      {
        category: '免费用户的所有功能',
        items: []
      },
      {
        category: '工业流程计算功能附加esi读取能力',
        items: [
          '可以配置想要读取的目标容器',
          '流程视图根据库存判断工作进度',
          '工作流根据库存判断原材料是否满足与蓝图是否缺失',
          '+ 成本视图：分析成本分布比例判断盈利空间',
          '+ 劳动力视图：提供输出向计划容器的所有正在进行的工作者信息，提供合作利益分配手段',
          '+ 物流视图：提供材料满足但是需要运输时的可执行方案',
          '+ 化矿视图：对矿石配平求解'
        ]
      }
    ],
    isPopular: true
  },
  {
    name: 'Omega订阅',
    price: '2B',
    priceUnit: 'Isk/月',
    color: '#e6a23c',
    hasTrial: true,
    trialText: '可领取7天试用',
    features: [
      {
        category: '免费用户与alpha订阅的全部功能',
        items: []
      },
      {
        category: '市场分析与利润分析',
        items: [
          '创建自选type的市场监控界面',
          '可选jita与FRT市场的价格拉取',
          '根据你的计划配置计算type成本与利润',
          '对单个type或清单内全量type的交易量、流水等分析（开发中）'
        ]
      }
    ],
    isPopular: false
  }
]
</script>

<template>
  <div class="landing-page">
    <!-- Hero 区域 -->
    <section class="hero-section">
      <div class="hero-container">
        <div class="hero-content">
          <h1 class="hero-title">
            <span class="title-main">Kahuna System</span>
            <span class="title-sub">EVE Online 工业辅助平台</span>
          </h1>
          <p class="hero-description">
            面向流程的工业辅助平台，以简单易懂的方式回答"我该搓什么"、"我该怎么搓"等核心问题，为熟练度不足或希望节省精力的玩家提供一整套易理解、可操作的执行方案
          </p>
          <div class="hero-actions">
            <el-button
              type="primary"
              size="large"
              @click="goToHome"
              class="hero-button"
            >
              {{ authStore.isAuthenticated ? '进入系统' : '立即开始' }}
            </el-button>
            <el-button
              size="large"
              @click="openGitHub"
              class="hero-button github-button"
              title="打开 GitHub 仓库"
            >
              <img :src="githubIconWhite" alt="GitHub" class="github-icon" />
              GitHub
            </el-button>
            <el-button
              v-if="showDonateButton"
              size="large"
              @click="openDonate"
              class="hero-button donate-button"
              title="支持作者"
            >
              <img :src="aifadianLogo" alt="爱发电" class="donate-icon" />
            </el-button>
          </div>
          <div class="hero-tagline">
            <span>🥰 爱来自 凛冬联盟群 紫竹梅重工</span>
          </div>
          <div class="hero-tagline" v-if="showQQGroupButton">
            <span>邀请码获取请加入QQ交流群：{{ QQGroupNumber }}</span>
          </div>
        </div>
        <div class="hero-image-wrapper">
          <div class="hero-image-container">
            <img :src="mainViewImage" alt="Kahuna System 主界面" class="hero-image" />
            <div class="hero-image-glow"></div>
          </div>
        </div>
      </div>
    </section>

    <!-- 功能展示区域 -->
    <section class="features-section">
      <div class="section-container">
        <h2 class="section-title">核心功能</h2>
        <p class="section-subtitle">为 EVE Online 玩家提供全方位的工业辅助服务</p>
        <div class="features-grid">
          <el-card
            v-for="(feature, index) in features"
            :key="index"
            shadow="hover"
            class="feature-card"
          >
            <!-- 功能图片区域 -->
            <div class="feature-image-wrapper">
              <!-- 资产管理功能：展示三张图片 -->
              <div v-if="feature.images" class="feature-images-multi">
                <div
                  v-for="(img, imgIndex) in feature.images"
                  :key="imgIndex"
                  class="feature-image-item"
                  @click="openPreview(feature.images, imgIndex)"
                >
                  <img :src="img" :alt="`${feature.title} - 图片 ${imgIndex + 1}`" class="feature-image" />
                  <div class="feature-image-overlay">
                    <el-icon :size="32" class="preview-icon">
                      <ZoomIn />
                    </el-icon>
                  </div>
                </div>
              </div>
              <!-- 单张图片功能 -->
              <div v-else class="feature-image-single" @click="openPreview(feature.image, 0)">
                <img :src="feature.image" :alt="feature.title" class="feature-image" />
                <div class="feature-image-overlay">
                  <el-icon :size="32" class="preview-icon">
                    <ZoomIn />
                  </el-icon>
                </div>
              </div>
            </div>
            <!-- 功能信息区域 -->
            <div class="feature-content">
              <div class="feature-icon" :style="{ color: feature.color }">
                <el-icon :size="48">
                  <component :is="feature.icon" />
                </el-icon>
              </div>
              <h3 class="feature-title">{{ feature.title }}</h3>
              <p class="feature-description">{{ feature.description }}</p>
            </div>
          </el-card>
        </div>
      </div>
      <!-- 图片预览对话框 -->
      <el-dialog
        v-model="previewVisible"
        :width="'90%'"
        :show-close="true"
        :close-on-click-modal="true"
        :close-on-press-escape="true"
        align-center
        class="image-preview-dialog"
        @close="previewVisible = false"
      >
        <div class="image-preview-container">
          <img
            v-for="(img, index) in previewImageList"
            :key="index"
            v-show="index === previewInitialIndex"
            :src="img"
            class="image-preview-img"
            @click.stop
          />
          <!-- 多图导航 -->
          <div v-if="previewImageList.length > 1" class="image-preview-nav">
            <el-button
              circle
              :disabled="previewInitialIndex === 0"
              @click="previewInitialIndex = Math.max(0, previewInitialIndex - 1)"
            >
              <el-icon><ArrowLeft /></el-icon>
            </el-button>
            <span class="image-preview-counter">
              {{ previewInitialIndex + 1 }} / {{ previewImageList.length }}
            </span>
            <el-button
              circle
              :disabled="previewInitialIndex === previewImageList.length - 1"
              @click="previewInitialIndex = Math.min(previewImageList.length - 1, previewInitialIndex + 1)"
            >
              <el-icon><ArrowRight /></el-icon>
            </el-button>
          </div>
        </div>
      </el-dialog>
    </section>

    <!-- 特色介绍区域 -->
    <section class="highlights-section">
      <div class="section-container">
        <h2 class="section-title">系统特色</h2>
        <p class="section-subtitle">让工业制造变得简单高效</p>
        <div class="highlights-grid">
          <div
            v-for="(highlight, index) in highlights"
            :key="index"
            class="highlight-item"
          >
            <div class="highlight-number">{{ index + 1 }}</div>
            <h3 class="highlight-title">{{ highlight.title }}</h3>
            <p class="highlight-description">{{ highlight.description }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- 定价展示区域 -->
    <section class="pricing-section">
      <div class="section-container">
        <h2 class="section-title">订阅方案</h2>
        <p class="section-subtitle">可领取Omega 7天试用</p>
        <p class="pricing-notice">
          收费策略可能会根据服务器资源、联盟政策等因素变动，暂不接受年卡等长期订阅
        </p>
        <div class="pricing-grid">
          <el-card
            v-for="(plan, index) in pricingPlans"
            :key="index"
            shadow="hover"
            :class="['pricing-card', { 'pricing-card-popular': plan.isPopular }]"
          >
            <div class="pricing-header" :style="{ borderTopColor: plan.color }">
              <h3 class="pricing-name">{{ plan.name }}</h3>
              <div class="pricing-price">
                <span class="price-amount">{{ plan.price }}</span>
                <span class="price-unit" v-if="plan.priceUnit">{{ plan.priceUnit }}</span>
              </div>
              <div v-if="plan.hasTrial" class="pricing-trial">
                {{ plan.trialText }}
              </div>
              <div v-if="plan.note" class="pricing-note">
                {{ plan.note }}
              </div>
            </div>
            <div class="pricing-features">
              <div
                v-for="(feature, featureIndex) in plan.features"
                :key="featureIndex"
                class="feature-group"
              >
                <h4 class="feature-category">{{ feature.category }}</h4>
                <ul v-if="feature.items && feature.items.length > 0" class="feature-list">
                  <li v-for="(item, itemIndex) in feature.items" :key="itemIndex" class="feature-item">
                    {{ item }}
                  </li>
                </ul>
              </div>
            </div>
          </el-card>
        </div>
      </div>
    </section>

    <!-- 页脚 -->
    <footer class="landing-footer">
      <div class="footer-content">
        <p>© 2025 Kahuna System. 紫竹梅重工.</p>
        <p class="footer-subtitle">基于 Quart 和 Vue3 的 EVE Online 一体化 Web 应用平台</p>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.landing-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

/* Hero 区域 */
.hero-section {
  min-height: 90vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 80px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  position: relative;
  overflow: hidden;
}

.hero-section::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: url('data:image/svg+xml,<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg"><defs><pattern id="grid" width="100" height="100" patternUnits="userSpaceOnUse"><path d="M 100 0 L 0 0 0 100" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="1"/></pattern></defs><rect width="100" height="100" fill="url(%23grid)"/></svg>');
  opacity: 0.3;
}

.hero-container {
  max-width: 1400px;
  width: 100%;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 60px;
  align-items: center;
  position: relative;
  z-index: 1;
}

.hero-content {
  text-align: left;
  position: relative;
  z-index: 1;
}

.hero-title {
  margin: 0 0 24px 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.title-main {
  font-size: 64px;
  font-weight: 700;
  color: white;
  text-shadow: 0 2px 20px rgba(0, 0, 0, 0.2);
  line-height: 1.2;
}

.title-sub {
  font-size: 28px;
  font-weight: 400;
  color: rgba(255, 255, 255, 0.9);
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.hero-description {
  font-size: 20px;
  color: rgba(255, 255, 255, 0.95);
  line-height: 1.8;
  margin: 0 0 40px 0;
  text-shadow: 0 1px 5px rgba(0, 0, 0, 0.1);
}

.hero-actions {
  display: flex;
  gap: 16px;
  justify-content: flex-start;
  margin-bottom: 32px;
}

.hero-button {
  padding: 16px 40px;
  font-size: 18px;
  font-weight: 500;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transition: all 0.3s ease;
}

.hero-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.2);
}

.hero-button.secondary {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.3);
  color: white;
  backdrop-filter: blur(10px);
}

.hero-button.secondary:hover {
  background: rgba(255, 255, 255, 0.3);
  border-color: rgba(255, 255, 255, 0.5);
}

.hero-button.github-button {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.3);
  color: white;
  backdrop-filter: blur(10px);
  display: flex;
  align-items: center;
  gap: 8px;
}

.hero-button.github-button:hover {
  background: rgba(255, 255, 255, 0.25);
  border-color: rgba(255, 255, 255, 0.5);
}

.hero-button.donate-button {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.3);
  color: white;
  backdrop-filter: blur(10px);
  display: flex;
  align-items: center;
  gap: 8px;
}

.hero-button.donate-button:hover {
  background: rgba(255, 255, 255, 0.25);
  border-color: rgba(255, 255, 255, 0.5);
}

.donate-icon {
  height: 80px;
  width: auto;
  object-fit: contain;
}

.github-icon {
  width: 20px;
  height: 20px;
  filter: brightness(0) invert(1);
}

.hero-tagline {
  margin-top: 24px;
  font-size: 16px;
  color: rgba(255, 255, 255, 0.8);
}

/* Hero 图片区域 */
.hero-image-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  perspective: 1000px;
}

.hero-image-container {
  position: relative;
  width: 100%;
  max-width: 700px;
  transform-style: preserve-3d;
  animation: float 6s ease-in-out infinite;
}

.hero-image {
  width: 100%;
  height: auto;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3),
              0 0 0 1px rgba(255, 255, 255, 0.1);
  object-fit: contain;
  display: block;
  position: relative;
  z-index: 2;
  transition: transform 0.3s ease;
}

.hero-image:hover {
  transform: translateY(-5px) scale(1.02);
}

.hero-image-glow {
  position: absolute;
  top: -20px;
  left: -20px;
  right: -20px;
  bottom: -20px;
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.4) 0%, rgba(118, 75, 162, 0.4) 100%);
  border-radius: 24px;
  filter: blur(30px);
  opacity: 0.6;
  z-index: 1;
  animation: pulse 3s ease-in-out infinite;
}

@keyframes float {
  0%, 100% {
    transform: translateY(0px) rotateY(0deg);
  }
  50% {
    transform: translateY(-20px) rotateY(2deg);
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 0.4;
    transform: scale(1);
  }
  50% {
    opacity: 0.7;
    transform: scale(1.05);
  }
}

/* 功能展示区域 */
.features-section {
  padding: 100px 24px;
  background: #f5f7fa;
}

.section-container {
  max-width: 1200px;
  margin: 0 auto;
}

.section-title {
  font-size: 42px;
  font-weight: 700;
  color: #2c3e50;
  text-align: center;
  margin: 0 0 16px 0;
}

.section-subtitle {
  font-size: 18px;
  color: #64748b;
  text-align: center;
  margin: 0 0 60px 0;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
  gap: 40px;
  margin-top: 40px;
}

.feature-card {
  border-radius: 16px;
  transition: all 0.3s ease;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: white;
}

.feature-card:hover {
  transform: translateY(-8px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.15);
}

/* 功能图片区域 */
.feature-image-wrapper {
  width: 100%;
  position: relative;
  overflow: hidden;
  background: #f8f9fa;
}

.feature-image-single {
  position: relative;
  width: 100%;
  cursor: pointer;
  overflow: hidden;
}

.feature-images-multi {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 8px;
}

.feature-image-item {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  cursor: pointer;
  overflow: hidden;
  border-radius: 8px;
  background: #f0f0f0;
}

.feature-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
  display: block;
}

.feature-image-single .feature-image {
  aspect-ratio: 16 / 9;
}

.feature-image-item:hover .feature-image,
.feature-image-single:hover .feature-image {
  transform: scale(1.05);
}

.feature-image-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.feature-image-item:hover .feature-image-overlay,
.feature-image-single:hover .feature-image-overlay {
  opacity: 1;
}

.preview-icon {
  color: white;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.3));
}

/* 功能内容区域 */
.feature-content {
  padding: 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.feature-icon {
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.feature-title {
  font-size: 24px;
  font-weight: 600;
  color: #2c3e50;
  margin: 0 0 12px 0;
}

.feature-description {
  font-size: 15px;
  color: #64748b;
  line-height: 1.6;
  margin: 0;
}

/* 图片预览对话框样式 */
:deep(.image-preview-dialog) {
  .el-dialog__body {
    padding: 0;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 70vh;
    background-color: rgba(0, 0, 0, 0.9);
  }
  
  .el-dialog__header {
    background-color: rgba(0, 0, 0, 0.9);
    color: white;
  }
  
  .el-dialog__close {
    color: white;
  }
}

.image-preview-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 20px;
  position: relative;
}

.image-preview-img {
  max-width: 100%;
  max-height: 75vh;
  width: auto;
  height: auto;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.image-preview-nav {
  position: absolute;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 20px;
  background: rgba(0, 0, 0, 0.6);
  padding: 12px 24px;
  border-radius: 24px;
  backdrop-filter: blur(10px);
}

.image-preview-counter {
  color: white;
  font-size: 16px;
  font-weight: 500;
  min-width: 60px;
  text-align: center;
}

/* 特色介绍区域 */
.highlights-section {
  padding: 100px 24px;
  background: white;
}

.highlights-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 40px;
  margin-top: 60px;
}

.highlight-item {
  text-align: center;
  position: relative;
}

.highlight-number {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 28px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 24px;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.highlight-title {
  font-size: 24px;
  font-weight: 600;
  color: #2c3e50;
  margin: 0 0 16px 0;
}

.highlight-description {
  font-size: 16px;
  color: #64748b;
  line-height: 1.8;
  margin: 0;
}

/* 定价展示区域 */
.pricing-section {
  padding: 100px 24px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
}

.pricing-notice {
  font-size: 14px;
  color: #909399;
  text-align: center;
  margin: 0 0 60px 0;
  font-style: italic;
}

.pricing-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 32px;
  margin-top: 40px;
  max-width: 1200px;
  margin-left: auto;
  margin-right: auto;
}

.pricing-card {
  border-radius: 16px;
  transition: all 0.3s ease;
  overflow: hidden;
  background: white;
  border: 2px solid transparent;
  position: relative;
}

.pricing-card:hover {
  transform: translateY(-8px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.15);
}

.pricing-card-popular {
  border-color: #409eff;
  box-shadow: 0 8px 24px rgba(64, 158, 255, 0.2);
}

.pricing-card-popular::before {
  content: '推荐';
  position: absolute;
  top: 16px;
  right: -32px;
  background: #409eff;
  color: white;
  padding: 4px 40px;
  font-size: 12px;
  font-weight: 600;
  transform: rotate(45deg);
  z-index: 10;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.3);
}

.pricing-header {
  padding: 32px 24px;
  text-align: center;
  border-top: 4px solid;
  background: linear-gradient(to bottom, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0.85));
}

.pricing-name {
  font-size: 24px;
  font-weight: 600;
  color: #2c3e50;
  margin: 0 0 16px 0;
}

.pricing-price {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 8px;
  margin-bottom: 16px;
}

.price-amount {
  font-size: 42px;
  font-weight: 700;
  color: #2c3e50;
  line-height: 1;
}

.price-unit {
  font-size: 16px;
  color: #64748b;
  font-weight: 500;
}

.pricing-trial {
  display: inline-block;
  background: linear-gradient(135deg, #e6a23c 0%, #f0c674 100%);
  color: white;
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  margin-top: 8px;
  box-shadow: 0 2px 8px rgba(230, 162, 60, 0.3);
}

.pricing-note {
  font-size: 12px;
  color: #909399;
  margin-top: 12px;
  line-height: 1.5;
}

.pricing-features {
  padding: 24px;
}

.feature-group {
  margin-bottom: 24px;
}

.feature-group:last-child {
  margin-bottom: 0;
}

.feature-category {
  font-size: 16px;
  font-weight: 600;
  color: #2c3e50;
  margin: 0 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #e4e7ed;
}

.feature-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.feature-item {
  font-size: 14px;
  color: #64748b;
  line-height: 1.8;
  padding: 6px 0;
  padding-left: 20px;
  position: relative;
}

.feature-item::before {
  content: '✓';
  position: absolute;
  left: 0;
  color: #67c23a;
  font-weight: 600;
}

/* 技术栈展示 */
.tech-section {
  padding: 80px 24px;
  background: #f5f7fa;
}

.tech-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  justify-content: center;
  margin-top: 40px;
}

.tech-tags .el-tag {
  padding: 12px 24px;
  font-size: 16px;
  font-weight: 500;
}

/* 页脚 */
.landing-footer {
  background: #2c3e50;
  color: rgba(255, 255, 255, 0.8);
  padding: 40px 24px;
  text-align: center;
}

.footer-content p {
  margin: 8px 0;
  font-size: 14px;
}

.footer-subtitle {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
}

/* 响应式设计 */
@media (max-width: 1024px) {
  .hero-container {
    grid-template-columns: 1fr;
    gap: 40px;
    text-align: center;
  }

  .hero-content {
    text-align: center;
  }

  .hero-actions {
    justify-content: center;
  }

  .hero-image-container {
    max-width: 100%;
  }
}

@media (max-width: 768px) {
  .hero-section {
    min-height: auto;
    padding: 60px 16px;
  }

  .title-main {
    font-size: 42px;
  }

  .title-sub {
    font-size: 20px;
  }

  .hero-description {
    font-size: 16px;
  }

  .hero-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-button {
    width: 100%;
  }

  .hero-container {
    gap: 30px;
  }

  .hero-image-container {
    max-width: 100%;
  }

  .section-title {
    font-size: 32px;
  }

  .features-grid {
    grid-template-columns: 1fr;
    gap: 24px;
  }

  .feature-images-multi {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .feature-content {
    padding: 24px;
  }

  .highlights-grid {
    grid-template-columns: 1fr;
  }
  
  .image-preview-nav {
    bottom: 20px;
    padding: 8px 16px;
  }
  
  .image-preview-img {
    max-height: 60vh;
  }

  .pricing-grid {
    grid-template-columns: 1fr;
    gap: 24px;
  }

  .pricing-card-popular::before {
    top: 12px;
    right: -28px;
    padding: 3px 35px;
    font-size: 11px;
  }

  .price-amount {
    font-size: 36px;
  }

  .pricing-header {
    padding: 24px 20px;
  }

  .pricing-features {
    padding: 20px;
  }
}

@media (max-width: 1024px) {
  .features-grid {
    grid-template-columns: 1fr;
    gap: 32px;
  }

  .pricing-grid {
    grid-template-columns: 1fr;
    gap: 28px;
  }
}
</style>

