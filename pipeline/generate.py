#!/usr/bin/env python3
"""
AI Paper Review & 60s Shorts Generator via Claude (Anthropic API)
Author: Donghwan Shin (@whizzkkid)
"""

import os
import re
import sys
import argparse
from datetime import datetime
import urllib.request
import xml.etree.ElementTree as ET

try:
    import anthropic
except ImportError:
    print("Error: 'anthropic' package is not installed. Run 'pip install -r requirements.txt'")
    sys.exit(1)


def fetch_arxiv_details(arxiv_id: str) -> dict:
    """Fetch paper title, authors, summary, and published date from arXiv API."""
    clean_id = re.sub(r"^arxiv:\s*", "", arxiv_id.strip(), flags=re.IGNORECASE)
    url = f"http://export.arxiv.org/api/query?id_list={clean_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "AI-Paper-Review-Bot/1.0"})
    
    with urllib.request.urlopen(req) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)
    entry = root.find("{http://www.w3.org/2005/Atom}entry")
    if entry is None:
        raise ValueError(f"Paper with arXiv ID '{clean_id}' not found.")

    title = entry.find("{http://www.w3.org/2005/Atom}title").text.strip().replace("\n", " ")
    summary = entry.find("{http://www.w3.org/2005/Atom}summary").text.strip().replace("\n", " ")
    published = entry.find("{http://www.w3.org/2005/Atom}published").text.strip()
    
    authors = []
    for author in entry.findall("{http://www.w3.org/2005/Atom}author"):
        name = author.find("{http://www.w3.org/2005/Atom}name").text.strip()
        authors.append(name)

    return {
        "id": clean_id,
        "title": title,
        "summary": summary,
        "authors": authors,
        "published": published[:10]
    }


def generate_review_and_shorts(paper: dict, model: str, api_key: str):
    """Call Claude API to generate both a Jekyll blog post and a 60-second shorts script."""
    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = """당신은 세계 최고 수준의 AI 연구자이자 테크 콘텐츠 크리에이터입니다.
주어진 최신 AI 학회 논문의 정보(제목, 저자, 초록)를 바탕으로 다음 두 가지 산출물을 작성하세요:

1. [BLOG POST]
- Jekyll GitHub Pages용 마크다운 포스팅
- 반드시 최상단에 YAML Frontmatter를 포함할 것:
  layout: post
  title: "[핵심 매력적인 한글 제목] 논문 영문 원제"
  date: YYYY-MM-DD HH:MM:SS +0900
  categories: [AI Research]
  tags: [태그1, 태그2, ...]
- 본문 구성:
  - 인트로: 일반인과 엔지니어 모두 직관적으로 이해할 수 있는 문제의식
  - 기존 방식의 한계 (왜 지금까지 안 되었는가?)
  - 핵심 아이디어 & 아키텍처 (Mermaid.js 다이어그램 1개 이상 포함)
  - 핵심 결과 및 벤치마크 (수식 및 정량적 수치 포함)
  - 실무자/연구자 관점의 시사점 및 미래 방향
  - TL;DR 요약 3줄

2. [SHORTS SCRIPT]
- 60초 유튜브 쇼츠 / 인스타 릴스용 낭독 대본 & 연출 가이드
- 타임라인 테이블 (0~6초 훅, 6~18초 문제의식, 18~42초 핵심 원리, 42~54초 결과, 54~60초 CTA)
- 화면 연출 지시문 (Visual/B-Roll)과 구어체 음성 대본
- 고정 댓글(Pinned Comment) 템플릿 포함

출력은 반드시 다음 마커로 구분하여 출력하세요:
<<<BLOG_POST_START>>>
(블로그 포스트 내용)
<<<BLOG_POST_END>>>

<<<SHORTS_SCRIPT_START>>>
(쇼츠 스크립트 내용)
<<<SHORTS_SCRIPT_END>>>
"""

    user_prompt = f"""다음 논문에 대해 블로그 리뷰 포스트와 60초 쇼츠 대본을 작성해 주세요:
- arXiv ID: {paper['id']}
- 제목: {paper['title']}
- 저자: {', '.join(paper['authors'][:5])}
- 발행일: {paper['published']}
- 초록(Abstract):
{paper['summary']}
"""

    print(f"[*] Calling Claude ({model}) to analyze paper '{paper['title']}'...")
    response = client.messages.create(
        model=model,
        max_tokens=4000,
        temperature=0.7,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )

    content = response.content[0].text

    blog_match = re.search(r"<<<BLOG_POST_START>>>(.*?)<<<BLOG_POST_END>>>", content, re.DOTALL)
    shorts_match = re.search(r"<<<SHORTS_SCRIPT_START>>>(.*?)<<<SHORTS_SCRIPT_END>>>", content, re.DOTALL)

    blog_text = blog_match.group(1).strip() if blog_match else ""
    shorts_text = shorts_match.group(1).strip() if shorts_match else ""

    return blog_text, shorts_text


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", slug).strip("-")[:40]


def main():
    parser = argparse.ArgumentParser(description="Generate AI Paper Review & Shorts using Claude API")
    parser.add_argument("--arxiv-id", required=True, help="arXiv paper ID (e.g., 2505.06120)")
    parser.add_argument("--model", default="claude-3-7-sonnet-20250219", help="Claude model name")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    print(f"[*] Fetching metadata for arXiv:{args.arxiv_id}...")
    paper = fetch_arxiv_details(args.arxiv_id)
    print(f"[+] Found: {paper['title']}")

    blog_post, shorts_script = generate_review_and_shorts(paper, args.model, api_key)

    today = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(paper['title'])

    # 1. Save Blog Post
    os.makedirs("_posts", exist_ok=True)
    post_filename = f"_posts/{today}-{slug}.md"
    with open(post_filename, "w", encoding="utf-8") as f:
        f.write(blog_post)
    print(f"[+] Saved Blog Post: {post_filename}")

    # 2. Save Shorts Script
    os.makedirs("shorts", exist_ok=True)
    shorts_filename = f"shorts/{today}-{slug}.md"
    with open(shorts_filename, "w", encoding="utf-8") as f:
        f.write(shorts_script)
    print(f"[+] Saved Shorts Script: {shorts_filename}")

    print("\n[🎉] Done! Blog post and shorts script generated successfully.")


if __name__ == "__main__":
    main()
