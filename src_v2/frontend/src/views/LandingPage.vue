<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  ArrowRight,
  Cpu,
  DataAnalysis,
  Money,
  ShoppingCart,
  Tools,
  TrendCharts,
  ZoomIn,
} from '@element-plus/icons-vue'
import VipPricingPlans from '@/components/VipPricingPlans.vue'
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
const previewVisible = ref(false)
const previewImageList = ref<string[]>([])
const previewInitialIndex = ref(0)

const GITHUB_REPO_URL = 'https://github.com/AraragiEro/EveKahunaSystem.git'
const donateLink = computed(() => import.meta.env.VITE_DONATE_LINK as string | undefined)
const qqGroupNumber = computed(() => import.meta.env.VITE_QQ_GROUP as string | undefined)

const showDonateButton = computed(() => !!donateLink.value)
const showQQGroupButton = computed(() => !!qqGroupNumber.value)

const openGitHub = () => window.open(GITHUB_REPO_URL, '_blank')
const openDonate = () => donateLink.value && window.open(donateLink.value, '_blank')
const goToHome = () => router.push(authStore.isAuthenticated ? '/home' : '/login')
const goToAnnouncements = () => router.push('/announcements')

const openPreview = (images: string | string[], index = 0) => {
  previewImageList.value = Array.isArray(images) ? images : [images]
  previewInitialIndex.value = index
  previewVisible.value = true
}

const features = [
  {
    icon: Cpu,
    title: '工业规划',
    description: '从目标产物自动拆解出制造链路，输出可执行的计划与报表。',
    image: industryPlanImage,
  },
  {
    icon: TrendCharts,
    title: '市场与利润分析',
    description: '多维价格视角和利润测算联动，快速定位可交易机会。',
    image: marketAnalysisImage,
  },
  {
    icon: Money,
    title: '成本计算',
    description: '统一汇总制造、采购、物流成本，让定价决策更可控。',
    image: costCalculationImage,
  },
  {
    icon: ShoppingCart,
    title: '采购清单',
    description: '一键生成可执行采购列表，减少生产准备时间。',
    image: procurementListImage,
  },
  {
    icon: DataAnalysis,
    title: '资产管理',
    description: '角色与公司资产联动统计，支持跨账号的库存掌控。',
    images: [assetManagementImage1, assetManagementImage2, assetManagementImage3],
  },
  {
    icon: Tools,
    title: '化矿与协作生产',
    description: '覆盖精炼计算与协作链路，让多人生产更稳定。',
    image: oreRefiningImage || cooperativeProductionImage,
  },
]
</script>

<template>
  <div class="landing-page">
    <section class="hero">
      <div class="hero-noise" />
      <div class="hero-grid" />
      <div class="hero-content">
        <div class="hero-text">
          <p class="eyebrow">Kahuna System</p>
          <h1>面向 EVE 工业的可执行决策平台</h1>
          <p class="desc">
            用统一的数据与流程，把“做什么、怎么做、赚不赚钱”这三件事讲清楚。
          </p>
          <div class="hero-actions">
            <el-button type="primary" size="large" class="cta-btn" @click="goToHome">
              {{ authStore.isAuthenticated ? '进入系统' : '立即开始' }}
              <el-icon><ArrowRight /></el-icon>
            </el-button>
            <el-button size="large" class="ghost-btn" @click="openGitHub">
              <img :src="githubIconWhite" alt="GitHub" class="github-icon" />
              GitHub
            </el-button>
            <el-button size="large" class="ghost-btn" @click="goToAnnouncements">公告</el-button>
            <el-button v-if="showDonateButton" size="large" class="ghost-btn donate" @click="openDonate">
              <img :src="aifadianLogo" alt="爱发电" class="donate-icon" />
            </el-button>
          </div>
          <p v-if="showQQGroupButton" class="qq-tip">邀请码获取请加入 QQ 交流群：{{ qqGroupNumber }}</p>
        </div>
        <div class="hero-card">
          <img :src="mainViewImage" alt="Kahuna 主界面预览" loading="eager" />
        </div>
      </div>
    </section>

    <section class="feature-section">
      <div class="section-header">
        <h2>核心能力</h2>
        <p>为工业链路提供从规划到执行的完整闭环</p>
      </div>
      <div class="feature-grid">
        <article v-for="(feature, index) in features" :key="feature.title + index" class="feature-card">
          <div class="feature-image-wrap">
            <div v-if="feature.images" class="multi-image-grid">
              <button
                v-for="(img, imgIndex) in feature.images"
                :key="imgIndex"
                type="button"
                class="feature-image-btn"
                @click="openPreview(feature.images, imgIndex)"
              >
                <img :src="img" :alt="`${feature.title}-${imgIndex + 1}`" loading="lazy" />
                <span class="zoom-layer"><el-icon><ZoomIn /></el-icon></span>
              </button>
            </div>
            <button v-else type="button" class="feature-image-btn" @click="openPreview(feature.image, 0)">
              <img :src="feature.image" :alt="feature.title" loading="lazy" />
              <span class="zoom-layer"><el-icon><ZoomIn /></el-icon></span>
            </button>
          </div>
          <div class="feature-body">
            <el-icon :size="26"><component :is="feature.icon" /></el-icon>
            <h3>{{ feature.title }}</h3>
            <p>{{ feature.description }}</p>
          </div>
        </article>
      </div>
    </section>

    <section class="pricing-section">
      <div class="section-header">
        <h2>订阅方案</h2>
        <p>支持试用，按阶段升级</p>
      </div>
      <VipPricingPlans />
    </section>

    <footer class="landing-footer">© 2026 Kahuna System</footer>

    <el-dialog v-model="previewVisible" width="88%" top="6vh" class="image-preview-dialog">
      <div class="preview-wrap">
        <img
          v-for="(img, index) in previewImageList"
          :key="img"
          v-show="index === previewInitialIndex"
          :src="img"
          alt="预览图"
          class="preview-img"
        />
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.landing-page {
  min-height: 100%;
  color: var(--k-color-text);
  background: var(--k-app-bg);
}

.hero {
  position: relative;
  min-height: 88dvh;
  overflow: hidden;
  background: var(--k-hero-bg);
}

.hero-noise {
  position: absolute;
  inset: 0;
  opacity: 0.16;
  background-image: radial-gradient(rgba(255, 255, 255, 0.4) 1px, transparent 1px);
  background-size: 3px 3px;
}

.hero-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.08) 1px, transparent 1px);
  background-size: 42px 42px;
  mask-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.9), transparent 85%);
}

.hero-content {
  position: relative;
  z-index: 1;
  max-width: 1240px;
  margin: 0 auto;
  padding: 90px 20px 70px;
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  gap: 38px;
  align-items: center;
}

.hero-text {
  color: #e8f2ff;
}

.eyebrow {
  margin: 0 0 12px;
  font-size: 13px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #98c8ff;
}

.hero-text h1 {
  margin: 0;
  font-size: clamp(34px, 6vw, 58px);
  line-height: 1.08;
  letter-spacing: 0.02em;
}

.desc {
  margin: 20px 0 0;
  max-width: 640px;
  font-size: 18px;
  line-height: 1.7;
  color: rgba(232, 242, 255, 0.92);
}

.hero-actions {
  margin-top: 30px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.cta-btn {
  height: 48px;
  border: 0;
  border-radius: 12px;
  background: linear-gradient(135deg, #2b74ff 0%, #36a9ff 100%);
  box-shadow: 0 12px 28px rgba(50, 125, 255, 0.35);
}

.ghost-btn {
  height: 48px;
  color: #dce9ff;
  border: 1px solid rgba(171, 199, 255, 0.4);
  border-radius: 12px;
  background: rgba(8, 22, 48, 0.36);
}

.github-icon {
  width: 16px;
  height: 16px;
}

.donate-icon {
  height: 30px;
  width: auto;
}

.qq-tip {
  margin-top: 16px;
  color: #a6c8ff;
}

.hero-card {
  position: relative;
  padding: 14px;
  border-radius: 20px;
  border: 1px solid rgba(131, 178, 255, 0.32);
  background: linear-gradient(145deg, rgba(12, 31, 68, 0.72), rgba(11, 27, 58, 0.4));
  box-shadow: 0 24px 64px rgba(4, 9, 24, 0.5);
}

.hero-card img {
  width: 100%;
  display: block;
  border-radius: 14px;
}

.feature-section,
.pricing-section {
  max-width: 1240px;
  margin: 0 auto;
  padding: 72px 20px 12px;
}

.section-header h2 {
  margin: 0;
  font-size: 34px;
}

.section-header p {
  margin: 10px 0 0;
  color: var(--k-color-text-secondary);
}

.feature-grid {
  margin-top: 26px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 16px;
}

.feature-card {
  overflow: hidden;
  border: 1px solid var(--k-color-border);
  border-radius: 14px;
  background: var(--k-color-surface);
  box-shadow: var(--k-shadow-sm);
}

.feature-image-wrap {
  background: var(--k-color-surface-soft);
}

.feature-image-btn {
  width: 100%;
  border: 0;
  padding: 0;
  display: block;
  position: relative;
  cursor: pointer;
  background: transparent;
}

.feature-image-btn img {
  width: 100%;
  height: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  display: block;
}

.zoom-layer {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #e8f2ff;
  opacity: 0;
  background: rgba(4, 14, 30, 0.5);
  transition: opacity 0.2s ease;
}

.feature-image-btn:hover .zoom-layer {
  opacity: 1;
}

.multi-image-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 8px;
}

.feature-body {
  padding: 14px 16px 18px;
}

.feature-body :deep(.el-icon) {
  color: var(--k-color-primary);
}

.feature-body h3 {
  margin: 8px 0 4px;
  font-size: 18px;
}

.feature-body p {
  margin: 0;
  color: var(--k-color-text-secondary);
  line-height: 1.6;
}

.pricing-section {
  padding-bottom: 64px;
}

.landing-footer {
  text-align: center;
  padding: 18px 20px 26px;
  border-top: 1px solid var(--k-color-border);
  color: var(--k-color-text-secondary);
}

.preview-wrap {
  min-height: 62dvh;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-img {
  max-width: 100%;
  max-height: 80dvh;
  object-fit: contain;
}

@media (max-width: 960px) {
  .hero-content {
    grid-template-columns: 1fr;
    padding-top: 70px;
  }

  .feature-grid {
    grid-template-columns: 1fr;
  }
}
</style>
