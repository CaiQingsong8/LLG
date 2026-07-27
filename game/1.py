# 运行 Claude（Token Plan 中转）
# 使用前请设置环境变量或配置到 .env：
#   ANTHROPIC_BASE_URL=https://token-plan-cn.xiaomimimo.com/anthropic
#   ANTHROPIC_API_KEY=你的_apikey
#
# 示例运行：
#   source .env && claude

ANTHROPIC_BASE_URL=https://token-plan-cn.xiaomimimo.com/anthropic \
    ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:?请设置 ANTHROPIC_API_KEY} \
    claude

echo ""
echo "退出后如需重新登录，请设置上述环境变量后执行:"
echo "  ANTHROPIC_BASE_URL=https://token-plan-cn.xiaomimimo.com/anthropic ANTHROPIC_API_KEY=\$YOUR_KEY claude"
