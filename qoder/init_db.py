"""
数据库初始化脚本
创建 seekdb (SQLite + FTS5) 和 PowerContext (SQLite) 所需的表结构
并插入示例数据
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from services.seekdb_service import SeekDBService
from services.powercontext_service import PowerContextService

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


def init_seekdb():
    """初始化 seekdb 数据库并插入示例数据"""
    print("步骤 1/3: 初始化 seekdb (SQLite + FTS5)...")

    db_path = os.path.join(DATA_DIR, 'seekdb.db')
    if os.path.exists(db_path):
        os.remove(db_path)

    seekdb = SeekDBService(db_path)

    sample_documents = [
        {
            'title': '深度学习入门指南',
            'content': '深度学习是机器学习的一个分支，它使用多层神经网络来学习数据的表示。本文将介绍深度学习的基本概念、常用模型和应用场景。我们将从神经网络的基础开始，逐步深入到卷积神经网络（CNN）和循环神经网络（RNN）等高级架构。深度学习在图像识别、自然语言处理、语音识别等领域取得了突破性进展。',
            'category': '人工智能',
            'tags': '深度学习,机器学习,神经网络,CNN,RNN'
        },
        {
            'title': 'Python 编程最佳实践',
            'content': 'Python 是一门流行的编程语言，以其简洁易读的语法著称。本文总结了 Python 编程的最佳实践，包括代码风格（PEP 8）、性能优化、错误处理、虚拟环境管理等方面。遵循这些实践可以帮助你写出更优雅、更高效的 Python 代码。我们还将讨论类型提示、装饰器、生成器等高级特性。',
            'category': '编程语言',
            'tags': 'Python,编程,最佳实践,代码质量,PEP8'
        },
        {
            'title': '自然语言处理技术综述',
            'content': '自然语言处理（NLP）是人工智能的重要研究方向，致力于让计算机理解和处理人类语言。本文综述了 NLP 领域的主要技术，包括文本分类、情感分析、机器翻译、问答系统、文本生成等。近年来，基于 Transformer 架构的大语言模型（如 GPT、BERT、LLaMA）在 NLP 领域取得了突破性进展，推动了整个 AI 行业的发展。',
            'category': '人工智能',
            'tags': 'NLP,自然语言处理,Transformer,GPT,BERT,大语言模型'
        },
        {
            'title': 'OceanBase 数据库架构解析',
            'content': 'OceanBase 是蚂蚁集团自主研发的分布式关系型数据库，具有高可用、高性能、高扩展性的特点。本文深入解析 OceanBase 的架构设计，包括分布式事务处理、多副本一致性协议（Paxos）、SQL 引擎优化、存储引擎设计等核心技术。OceanBase 兼容 MySQL 和 Oracle 协议，广泛应用于金融、电商等领域。',
            'category': '数据库',
            'tags': 'OceanBase,分布式数据库,MySQL兼容,Paxos,数据库架构'
        },
        {
            'title': '机器学习算法详解',
            'content': '机器学习是人工智能的核心技术之一，它使计算机能够从数据中学习并改进性能。本文详细讲解了常用的机器学习算法，包括线性回归、逻辑回归、决策树、支持向量机（SVM）、随机森林、梯度提升树（GBDT）等。对每种算法的原理、数学推导、优缺点和适用场景进行了深入分析，并附带 Python 代码实现。',
            'category': '人工智能',
            'tags': '机器学习,算法,监督学习,无监督学习,回归,分类'
        },
        {
            'title': 'Web 开发技术演进',
            'content': 'Web 开发技术在过去几十年中经历了巨大的变化。从最初的静态 HTML 页面，到动态网页（CGI、ASP、JSP）、Web 2.0（AJAX）、单页应用（SPA，React/Vue/Angular），再到如今的 Progressive Web App（PWA）、服务端渲染（SSR/Next.js/Nuxt）和全栈框架。本文回顾了 Web 开发技术的发展历程，并探讨了 WebAssembly、Edge Computing 等未来趋势。',
            'category': '编程语言',
            'tags': 'Web开发,前端,后端,React,Vue,SPA,PWA,SSR'
        },
        {
            'title': '云计算架构设计指南',
            'content': '云计算已经成为现代企业 IT 基础设施的重要组成部分。本文介绍了云计算的基本概念、服务模型（IaaS、PaaS、SaaS、FaaS）和部署模型（公有云、私有云、混合云、多云）。同时讨论了云原生架构设计的原则，包括微服务、容器化（Docker/Kubernetes）、DevOps、服务网格（Service Mesh）、可观测性等核心实践。',
            'category': '技术',
            'tags': '云计算,云原生,Kubernetes,Docker,微服务,DevOps'
        },
        {
            'title': '数据科学方法论与实践',
            'content': '数据科学是一个跨学科的领域，结合了统计学、机器学习和数据分析的方法，从数据中提取知识和洞察。本文介绍了数据科学的完整方法论，包括问题定义、数据收集与清洗、探索性数据分析（EDA）、特征工程、模型选择与训练、评估与验证、模型部署与监控。通过实际案例（如房价预测、用户流失分析）展示如何应用数据科学方法解决业务问题。',
            'category': '数据科学',
            'tags': '数据科学,方法论,数据分析,特征工程,模型部署'
        },
        {
            'title': 'PowerContext 上下文服务入门',
            'content': 'PowerContext 是一个面向 AI Agent 的开源上下文服务，它让工作上下文跨会话、跨智能体持续存在。核心概念包括 Scope（隔离空间）、Atomic Memory（原子记忆）、Source（证据来源）、Handoff（工作交接）和 Experience（经验积累）。通过 HTTP API、MCP 或 Python SDK 接入，Agent 可以保存决策、约束和进展，下次会话可以直接从当前状态继续。',
            'category': '技术',
            'tags': 'PowerContext,AI Agent,上下文管理,记忆服务,开源'
        },
        {
            'title': 'seekdb 混合检索技术',
            'content': 'seekdb 是一个支持向量检索、全文检索和结构化查询的混合检索数据库。它兼容 MySQL 协议，提供嵌入式、服务端和 Docker 等部署方式。seekdb 的核心优势在于将向量相似度搜索和传统 SQL 查询融合在一起，支持加权混合排序。适用于知识库搜索、文档检索、智能推荐等场景，是构建 AI 应用的理想数据基础设施。',
            'category': '数据库',
            'tags': 'seekdb,混合检索,向量检索,全文检索,MySQL兼容'
        },
        {
            'title': '计算机科学学习方法论',
            'content': '本文总结了高效学习计算机科学的方法，包括：理论与实践结合（每学一个概念就写代码验证）、建立知识图谱（将新知识与已有知识关联）、费曼学习法（用简单语言解释复杂概念）、项目驱动学习（通过实际项目掌握技术栈）。同时推荐了经典学习资源，如 MIT 6.824、CS231n、CS229 等公开课，以及 LeetCode、Kaggle 等实践平台。',
            'category': '学习方法',
            'tags': '计算机科学,学习方法,费曼技巧,项目驱动,公开课'
        },
        {
            'title': '论文写作与学术规范',
            'content': '本文介绍了学术论文写作的完整流程和学术规范。包括：选题与文献综述方法、论文结构（摘要、引言、方法、实验、结论）、LaTeX 排版技巧、图表制作规范、引用格式（APA、IEEE、GB/T 7714）、学术诚信与查重。同时分享了投稿策略、审稿意见回复技巧，以及常见期刊和会议的投稿要求。',
            'category': '学习方法',
            'tags': '论文写作,学术规范,LaTeX,文献综述,投稿'
        },
    ]

    for doc in sample_documents:
        doc_id = seekdb.add_document(**doc)
        if doc_id:
            print(f"  ✓ 文档 [{doc_id}] {doc['title']}")
        else:
            print(f"  ✗ 文档 {doc['title']} 插入失败")

    stats = seekdb.get_statistics()
    print(f"  seekdb 初始化完成: {stats['total_documents']} 篇文档")
    return seekdb


def init_powercontext():
    """初始化 PowerContext 数据库并创建示例记忆"""
    print("\n步骤 2/3: 初始化 PowerContext (本地上下文服务)...")

    db_path = os.path.join(DATA_DIR, 'powercontext.db')
    if os.path.exists(db_path):
        os.remove(db_path)

    pc = PowerContextService(db_path)

    demo_user = 'demo_user'
    pc._ensure_scope(demo_user)

    pc.save_user_preferences(demo_user, {
        'interests': '人工智能,数据库,Web开发',
        'learning_goal': 'systematic',
        'updated_at': '2026-11-02T00:00:00'
    })
    print(f"  ✓ 用户偏好已保存")

    pc.save_learning_progress(demo_user, 1, 0.75, 75)
    pc.save_learning_progress(demo_user, 3, 0.50, 50)
    pc.save_learning_progress(demo_user, 5, 1.0, 100)
    print(f"  ✓ 学习进度已保存 (3 篇文档)")

    pc.add_search_history(demo_user, '深度学习', 3)
    pc.add_search_history(demo_user, 'Python 编程', 2)
    pc.add_search_history(demo_user, '数据库架构', 4)
    print(f"  ✓ 搜索历史已保存 (3 条)")

    pc.add_viewed_documents(demo_user, 1, 1200)
    pc.add_viewed_documents(demo_user, 3, 800)
    pc.add_viewed_documents(demo_user, 5, 3600)
    pc.add_viewed_documents(demo_user, 9, 600)
    print(f"  ✓ 浏览记录已保存 (4 篇文档)")

    stats = pc.get_user_statistics(demo_user)
    print(f"  PowerContext 初始化完成: {stats['total_documents_viewed']} 篇已浏览, {stats['total_searches']} 次搜索")
    return pc


def verify():
    """验证初始化结果"""
    print("\n步骤 3/3: 验证初始化结果...")

    seekdb = SeekDBService()
    stats = seekdb.get_statistics()
    assert stats['total_documents'] > 0, "seekdb 中没有文档"
    print(f"  ✓ seekdb: {stats['total_documents']} 篇文档, {len(stats['categories'])} 个分类")

    categories = seekdb.get_all_categories()
    print(f"  ✓ 分类列表: {', '.join(categories)}")

    results = seekdb.hybrid_search(query='深度学习')
    print(f"  ✓ 搜索 '深度学习': {len(results)} 个结果")
    if results:
        print(f"    最佳匹配: {results[0]['title']} (score: {results[0]['final_score']:.4f})")

    pc = PowerContextService()
    memories = pc.get_all_memories('demo_user')
    print(f"  ✓ PowerContext demo_user: {len(memories)} 条记忆")

    recall = pc.recall_context('demo_user')
    print(f"  ✓ Recall manifest: {recall['total']} 条上下文")

    search_results = pc.search_memory('demo_user', '学习')
    print(f"  ✓ 记忆搜索 '学习': {len(search_results)} 条结果")


def main():
    print("=" * 60)
    print("智能知识库 - 数据库初始化")
    print("=" * 60)
    print()

    os.makedirs(DATA_DIR, exist_ok=True)

    init_seekdb()
    init_powercontext()
    verify()

    print()
    print("=" * 60)
    print("数据库初始化完成！")
    print("=" * 60)
    print()
    print("接下来可以运行：")
    print("  python app.py          # 启动 Flask 应用")
    print()


if __name__ == '__main__':
    main()
