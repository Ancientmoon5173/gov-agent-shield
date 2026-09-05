"""set_page_config 的安全封装。

Streamlit 多页面/重跑场景下，同一脚本执行上下文可能因重复调用或
“非首个 Streamlit 命令”而抛出 StreamlitAPIException，导致整页崩溃。
这里捕获该异常并放行：
- 正常场景：与直接调用 st.set_page_config 完全一致；
- 异常场景：页面配置通常已由同一次运行的首次调用生效，不再阻断渲染。
"""


def safe_set_page_config(**kwargs):
    import streamlit as st

    try:
        st.set_page_config(**kwargs)
    except Exception:
        # Streamlit 判定 set_page_config 不允许再次调用时触发；
        # 此时配置一般已生效，放行避免整页异常。
        pass
