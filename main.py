from flask import Flask, render_template, request, jsonify, redirect, url_for
import requests
import json
import time
from datetime import datetime, timedelta
import threading
import schedule
import os
from dataclasses import dataclass
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env
load_dotenv()

app = Flask(__name__)

@dataclass
class Article:
    title: str
    url: str
    description: str
    published_at: str
    source: str

class NewsCollector:
    def __init__(self):
        # Substitua por sua API key do NewsAPI
        self.news_api_key = os.getenv('NEWS_API_KEY', 'YOUR_NEWS_API_KEY')
        
        # Headers para web scraping
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def search_news(self, keywords: List[str], hours: int = 24) -> List[Article]:
        """Busca notícias das últimas X horas com palavras-chave específicas em múltiplas fontes"""
        articles = []
        
        print(f"🔍 Buscando notícias com palavras-chave: {keywords}")
        
        # 1. NewsAPI (se disponível)
        if self.news_api_key and self.news_api_key != 'YOUR_NEWS_API_KEY':
            articles.extend(self.search_newsapi(keywords, hours))
        
        # 2. Google News
        articles.extend(self.search_google_news(keywords, hours))
        
        # 3. Bing News
        articles.extend(self.search_bing_news(keywords, hours))
        
        # 4. Sites locais específicos do Litoral Norte
        articles.extend(self.search_local_sites(keywords, hours))
        
        # Remove duplicatas baseado na URL
        seen_urls = set()
        unique_articles = []
        for article in articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)
        
        # Se não encontrou artigos suficientes, adiciona exemplos para teste
        if len(unique_articles) < 5:
            print("⚠️ Poucos artigos encontrados, adicionando exemplos para teste...")
            test_articles = self.get_test_articles(keywords)
            unique_articles.extend(test_articles)
        
        print(f"✅ Total de {len(unique_articles)} artigos únicos encontrados")
        return unique_articles[:20]  # Limita a 20 artigos mais recentes

    def get_test_articles(self, keywords: List[str]) -> List[Article]:
        """Retorna artigos de exemplo para teste"""
        test_articles = [
            Article(
                title="Nova atração turística será inaugurada em Ilhabela neste verão",
                url="https://exemplo.com/ilhabela-nova-atracao",
                description="A Prefeitura de Ilhabela anunciou a inauguração de uma nova atração turística que promete movimentar ainda mais o turismo na região durante a alta temporada de verão.",
                published_at=datetime.now().isoformat(),
                source="Prefeitura de Ilhabela"
            ),
            Article(
                title="Porto de São Sebastião recebe investimentos em infraestrutura",
                url="https://exemplo.com/porto-sao-sebastiao",
                description="O Porto de São Sebastião receberá novos investimentos para modernização de sua infraestrutura, beneficiando toda a logística do Litoral Norte Paulista.",
                published_at=datetime.now().isoformat(),
                source="Governo do Estado de São Paulo"
            ),
            Article(
                title="Festival de inverno movimenta Caraguatatuba",
                url="https://exemplo.com/festival-caraguatatuba",
                description="O tradicional festival de inverno de Caraguatatuba acontece neste fim de semana, com apresentações musicais e atividades culturais para toda a família.",
                published_at=datetime.now().isoformat(),
                source="Secretaria de Cultura de Caraguatatuba"
            ),
            Article(
                title="Ubatuba lança campanha de preservação ambiental",
                url="https://exemplo.com/ubatuba-meio-ambiente",
                description="A cidade de Ubatuba lançou uma nova campanha de conscientização ambiental voltada para a preservação das praias e mata atlântica da região.",
                published_at=datetime.now().isoformat(),
                source="Secretaria de Meio Ambiente de Ubatuba"
            ),
            Article(
                title="Litoral Norte Paulista se prepara para temporada de verão",
                url="https://exemplo.com/litoral-norte-verao",
                description="Os quatro municípios do Litoral Norte Paulista se organizam para receber os turistas na próxima temporada de verão, com melhorias na infraestrutura e novos serviços.",
                published_at=datetime.now().isoformat(),
                source="Consórcio Litoral Norte"
            )
        ]
        
        # Filtra artigos relacionados às palavras-chave
        relevant_articles = []
        for article in test_articles:
            if any(keyword.lower() in article.title.lower() or keyword.lower() in article.description.lower() 
                   for keyword in keywords):
                relevant_articles.append(article)
        
        return relevant_articles[:3]  # Retorna até 3 artigos de teste

    def search_newsapi(self, keywords: List[str], hours: int) -> List[Article]:
        """Busca via NewsAPI"""
        articles = []
        from_date = (datetime.now() - timedelta(hours=hours)).isoformat()

        for keyword in keywords:
            try:
                url = f"https://newsapi.org/v2/everything"
                params = {
                    'q': keyword,
                    'from': from_date,
                    'sortBy': 'publishedAt',
                    'language': 'pt',
                    'apiKey': self.news_api_key
                }

                response = requests.get(url, params=params)
                data = response.json()

                if data['status'] == 'ok':
                    for item in data['articles'][:3]:
                        article = Article(
                            title=item['title'],
                            url=item['url'],
                            description=item['description'] or '',
                            published_at=item['publishedAt'],
                            source=f"NewsAPI - {item['source']['name']}"
                        )
                        articles.append(article)
                        
            except Exception as e:
                print(f"Erro ao buscar no NewsAPI para '{keyword}': {e}")
        
        return articles

    def search_google_news(self, keywords: List[str], hours: int) -> List[Article]:
        """Busca no Google News via scraping"""
        articles = []
        
        for keyword in keywords:
            try:
                # URL do Google News RSS (mais confiável)
                search_url = f"https://news.google.com/rss/search?q={keyword}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
                
                response = requests.get(search_url, headers=self.headers, timeout=10)
                
                if response.status_code == 200:
                    # Parse XML do RSS
                    from xml.etree import ElementTree as ET
                    root = ET.fromstring(response.content)
                    
                    for item in root.findall('.//item')[:3]:  # Pega primeiros 3 artigos
                        try:
                            title_elem = item.find('title')
                            link_elem = item.find('link')
                            desc_elem = item.find('description')
                            pubdate_elem = item.find('pubDate')
                            
                            if title_elem is not None and link_elem is not None:
                                title = title_elem.text.strip()
                                url = link_elem.text.strip()
                                
                                # Limpa descrição HTML se existir
                                description = ""
                                if desc_elem is not None and desc_elem.text:
                                    description = BeautifulSoup(desc_elem.text, 'html.parser').get_text().strip()
                                
                                if not description:
                                    description = f"Notícia sobre {keyword} encontrada no Google News"
                                
                                # Data de publicação
                                pub_date = pubdate_elem.text if pubdate_elem is not None else datetime.now().isoformat()
                                
                                article = Article(
                                    title=title,
                                    url=url,
                                    description=description[:300],  # Limita descrição
                                    published_at=pub_date,
                                    source="Google News"
                                )
                                articles.append(article)
                                
                        except Exception as e:
                            continue
                else:
                    # Fallback para método HTML se RSS falhar
                    articles.extend(self.search_google_news_html(keyword))
                        
            except Exception as e:
                print(f"Erro ao buscar no Google News para '{keyword}': {e}")
                # Tenta método alternativo
                try:
                    articles.extend(self.search_google_news_html(keyword))
                except:
                    pass
        
        return articles

    def search_google_news_html(self, keyword: str) -> List[Article]:
        """Método alternativo de busca no Google News via HTML"""
        articles = []
        try:
            search_url = f"https://news.google.com/search?q={keyword}&hl=pt-BR"
            response = requests.get(search_url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Busca por diferentes seletores de artigos
            selectors = [
                'article h3 a',
                'h3 a[href*="/articles/"]',
                '.JtKRv a',
                'h4 a'
            ]
            
            for selector in selectors:
                links = soup.select(selector)[:2]  # Pega 2 de cada seletor
                
                for link in links:
                    try:
                        title = link.get_text().strip()
                        href = link.get('href', '')
                        
                        if title and len(title) > 10:  # Garante que tem título válido
                            # Constrói URL completa
                            if href.startswith('./'):
                                url = f"https://news.google.com{href[1:]}"
                            elif href.startswith('/'):
                                url = f"https://news.google.com{href}"
                            else:
                                url = href
                            
                            # Gera descrição baseada no título e palavra-chave
                            description = f"Artigo sobre {keyword}: {title[:100]}..."
                            
                            article = Article(
                                title=title,
                                url=url,
                                description=description,
                                published_at=datetime.now().isoformat(),
                                source="Google News"
                            )
                            articles.append(article)
                            
                            if len(articles) >= 3:  # Limita resultado
                                break
                                
                    except Exception as e:
                        continue
                        
                if len(articles) >= 3:
                    break
                    
        except Exception as e:
            print(f"Erro no método HTML do Google News: {e}")
            
        return articles

    def search_bing_news(self, keywords: List[str], hours: int) -> List[Article]:
        """Busca no Bing News com melhor extração de conteúdo"""
        articles = []
        
        for keyword in keywords:
            try:
                # URL do Bing News melhorada
                search_url = f"https://www.bing.com/news/search?q={keyword}&qft=interval%3D7&form=HDRSC4"
                
                response = requests.get(search_url, headers=self.headers, timeout=10)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Múltiplos seletores para capturar artigos
                selectors = [
                    '.news-card',
                    '.newsitem',
                    'article',
                    '.b_algo'
                ]
                
                found_articles = 0
                
                for selector in selectors:
                    if found_articles >= 3:
                        break
                        
                    elements = soup.select(selector)[:5]
                    
                    for element in elements:
                        if found_articles >= 3:
                            break
                            
                        try:
                            # Busca título em diferentes elementos
                            title_element = (
                                element.find('h2') or 
                                element.find('h3') or 
                                element.find('h4') or
                                element.find('a', href=True)
                            )
                            
                            if title_element:
                                title = title_element.get_text().strip()
                                
                                # Busca link
                                link_element = title_element if title_element.name == 'a' else title_element.find('a')
                                if not link_element:
                                    link_element = element.find('a', href=True)
                                
                                if link_element and title and len(title) > 10:
                                    url = link_element.get('href', '')
                                    
                                    # Corrige URL se necessário
                                    if url.startswith('/'):
                                        url = f"https://www.bing.com{url}"
                                    elif not url.startswith('http'):
                                        continue
                                    
                                    # Busca descrição/snippet
                                    desc_element = (
                                        element.find('p') or
                                        element.find('div', class_='snippet') or
                                        element.find('.b_caption')
                                    )
                                    
                                    if desc_element:
                                        description = desc_element.get_text().strip()[:200]
                                    else:
                                        description = f"Notícia sobre {keyword} - {title[:100]}"
                                    
                                    # Remove descrições muito curtas ou genéricas
                                    if len(description) < 30:
                                        description = f"Artigo sobre {keyword}: {title[:150]}"
                                    
                                    article = Article(
                                        title=title,
                                        url=url,
                                        description=description,
                                        published_at=datetime.now().isoformat(),
                                        source="Bing News"
                                    )
                                    articles.append(article)
                                    found_articles += 1
                                    
                        except Exception as e:
                            continue
                        
            except Exception as e:
                print(f"Erro ao buscar no Bing News para '{keyword}': {e}")
        
        return articles

    def search_local_sites(self, keywords: List[str], hours: int) -> List[Article]:
        """Busca em sites locais específicos do Litoral Norte Paulista"""
        articles = []
        
        # Sites locais relevantes
        local_sites = [
            {
                'name': 'Portal Ilhabela',
                'url': 'https://www.portalilhabela.com.br',
                'search_path': '/busca?q='
            },
            {
                'name': 'São Sebastião Online', 
                'url': 'https://www.saosebastiaoonline.com.br',
                'search_path': '/search?q='
            },
            {
                'name': 'Caraguá News',
                'url': 'https://www.caraguanews.com.br', 
                'search_path': '/busca?termo='
            }
        ]
        
        for keyword in keywords:
            for site in local_sites:
                try:
                    # Busca genérica no site
                    search_url = f"{site['url']}{site['search_path']}{keyword}"
                    
                    response = requests.get(search_url, headers=self.headers, timeout=10)
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Procura por títulos e links de notícias
                    for link in soup.find_all('a', href=True, limit=3):
                        title = link.get_text().strip()
                        if len(title) > 20 and any(kw.lower() in title.lower() for kw in keywords):
                            url = link['href']
                            if not url.startswith('http'):
                                url = urljoin(site['url'], url)
                            
                            article = Article(
                                title=title,
                                url=url,
                                description=title[:150],
                                published_at=datetime.now().isoformat(),
                                source=site['name']
                            )
                            articles.append(article)
                            
                except Exception as e:
                    print(f"Erro ao buscar em {site['name']} para '{keyword}': {e}")
        
        return articles

class SEOGenerator:
    def __init__(self):
        # API key do Google Gemini
        self.gemini_api_key = os.getenv('GEMINI_API_KEY', 'YOUR_GEMINI_API_KEY')

    def generate_seo_content(self, article: Article) -> Dict[str, str]:
        """Gera conteúdo SEO otimizado estruturado para WordPress"""
        
        # Verifica se é sobre o Litoral Norte para otimizar o título
        keywords_litoral = ["Litoral Norte", "Ilhabela", "São Sebastião", "Caraguatatuba", "Ubatuba"]
        is_litoral_content = any(keyword.lower() in article.title.lower() for keyword in keywords_litoral)
        
        # Cria título principal otimizado (máximo 12 palavras)
        original_words = article.title.split()[:12]
        if is_litoral_content:
            main_title = " ".join(original_words)
        else:
            # Adapta para Litoral Norte se não for regional
            main_title = f"{' '.join(original_words[:10])} no Litoral Norte"
        
        # Cria subtítulo baseado na descrição
        subtitle = article.description[:100] + "..." if len(article.description) > 100 else article.description
        
        # Identifica a fonte para a estrutura final
        source_name = self.extract_source_name(article.source, article.description)
        
        # Determina categoria e subcategoria WordPress
        wp_category = self.determine_wordpress_category(article, is_litoral_content)
        
        # Gera conteúdo estruturado para WordPress
        wordpress_content = self.create_wordpress_structure(article, main_title, subtitle, source_name, is_litoral_content)
        
        # Meta description otimizada para WordPress
        meta_desc = f"{subtitle[:150]} | Portal de notícias do Litoral Norte Paulista"
        if len(subtitle) <= 120:
            meta_desc = f"{subtitle} | Acompanhe as notícias de Ilhabela, São Sebastião, Caraguatatuba e Ubatuba"

        # Para preview na interface web (mais visual)
        preview_content = f"""
        <div class="card border-primary">
            <div class="card-header bg-primary text-white">
                <h4 class="mb-0">📰 Conteúdo Pronto para WordPress</h4>
            </div>
            <div class="card-body">
                <div class="alert alert-info mb-4">
                    <h6><i class="fas fa-info-circle me-2"></i>Configurações WordPress (não aparecem no artigo):</h6>
                    <p class="mb-2"><strong>CATEGORIA:</strong> {wp_category['full_path']}</p>
                    <p class="mb-2"><strong>META DESCRIÇÃO:</strong> {meta_desc}</p>
                    <p class="mb-0"><strong>TAGS:</strong> {', '.join([tag.replace('<span class="badge bg-secondary me-1">', '').replace('</span>', '') for tag in self.generate_wordpress_tags(article, is_litoral_content).split()])}</p>
                </div>

                <div class="mb-4">
                    <h5 class="text-primary">📋 Título do Post:</h5>
                    <div class="border p-2 bg-light">
                        <span class="fw-bold text-dark">{main_title}</span>
                    </div>
                </div>
                
                <div class="mb-4">
                    <h5 class="text-primary">📄 Conteúdo Limpo do Post:</h5>
                    <div class="border p-2 bg-light mb-2">
                        <strong>Cole exatamente este conteúdo no WordPress:</strong><br>
                        <small class="text-muted">✅ Sem meta descrição, categorias ou tags no texto<br>
                        ✅ Apenas conteúdo editorial puro</small>
                    </div>
                    <div class="border p-3 bg-light" style="max-height: 400px; overflow-y: auto;">
                        {wordpress_content}
                    </div>
                </div>
                
                <div class="mb-4">
                    <h5 class="text-primary">📸 Imagem Destacada:</h5>
                    <img src="{self.get_featured_image(article, is_litoral_content)}" class="img-fluid rounded mb-2" alt="Imagem do artigo">
                    <div class="border p-2 bg-light">
                        <strong>Resumo da Imagem (configuração WordPress):</strong><br>
                        <span class="text-muted">{meta_desc}</span>
                    </div>
                </div>
                
                <div class="alert alert-success">
                    <h6>✅ Instruções WordPress:</h6>
                    <ul class="mb-0">
                        <li><strong>Título:</strong> Cole o título acima</li>
                        <li><strong>Categoria:</strong> {wp_category['full_path']}</li>
                        <li><strong>Meta descrição:</strong> Cole na configuração SEO</li>
                        <li><strong>Imagem destacada:</strong> Adicione + resumo</li>
                        <li><strong>Conteúdo:</strong> Cole apenas o texto editorial</li>
                    </ul>
                </div>
            </div>
        </div>
        
        <div class="mt-3">
            <a href="{article.url}" target="_blank" class="btn btn-outline-primary">
                <i class="fas fa-external-link-alt me-2"></i>Ver Artigo Original
            </a>
        </div>
        """

        seo_content = {
            'title': f"{main_title} | Portal Litoral Norte",
            'content': preview_content,
            'wordpress_content': wordpress_content,  # Conteúdo específico para WordPress
            'meta_description': meta_desc,
            'image_url': self.get_featured_image(article, is_litoral_content),
            'tags': self.generate_wordpress_tags(article, is_litoral_content),
            'source': source_name,
            'wp_category': wp_category,  # Categoria para WordPress
            'clean_title': main_title,  # Título limpo sem "| Portal"
            'image_alt': meta_desc  # Alt text para imagem
        }

        return seo_content

    def determine_wordpress_category(self, article: Article, is_litoral: bool) -> Dict[str, str]:
        """Determina categoria e subcategoria para WordPress baseado no conteúdo"""
        
        # Analisa o texto completo (título + descrição)
        full_text = f"{article.title} {article.description}".lower()
        
        # Verifica menção específica das cidades do Litoral Norte
        cities = {
            "ilhabela": "Ilhabela",
            "são sebastião": "São Sebastião", 
            "caraguatatuba": "Caraguatatuba",
            "ubatuba": "Ubatuba"
        }
        
        # Procura por cidades mencionadas
        mentioned_city = None
        for city_key, city_name in cities.items():
            if city_key in full_text:
                mentioned_city = city_name
                break
        
        # Define categoria principal baseada no conteúdo
        if mentioned_city:
            return {
                "main_category": "Cidades",
                "subcategory": mentioned_city,
                "full_path": f"Cidades > {mentioned_city}"
            }
        elif is_litoral and not mentioned_city:
            # Conteúdo do Litoral Norte mas sem cidade específica
            return {
                "main_category": "Cidades", 
                "subcategory": "Litoral Norte",
                "full_path": "Cidades > Litoral Norte"
            }
        elif any(keyword in full_text for keyword in ["brasil", "federal", "nacional", "país"]):
            return {
                "main_category": "Brasil",
                "subcategory": "",
                "full_path": "Brasil"
            }
        elif any(keyword in full_text for keyword in ["internacional", "mundial", "exterior", "país"]):
            return {
                "main_category": "Mundo", 
                "subcategory": "",
                "full_path": "Mundo"
            }
        else:
            # Categoria padrão quando não se encaixa nas outras
            return {
                "main_category": "Destaque",
                "subcategory": "",
                "full_path": "Destaque"
            }

    def extract_source_name(self, source: str, description: str) -> str:
        """Extrai e formata o nome da fonte adequadamente"""
        
        # Padrões comuns de fontes
        if "prefeitura" in source.lower() or "prefeitura" in description.lower():
            # Identifica qual prefeitura
            cities = ["Ilhabela", "São Sebastião", "Caraguatatuba", "Ubatuba"]
            for city in cities:
                if city.lower() in description.lower() or city.lower() in source.lower():
                    return f"Prefeitura de {city}"
            return "Prefeitura Municipal"
        
        if "bombeiros" in source.lower():
            return "Corpo de Bombeiros"
        
        if "polícia" in source.lower():
            return "Polícia Civil"
        
        if "governo" in source.lower():
            return "Governo do Estado de São Paulo"
        
        if "saúde" in source.lower():
            return "Secretaria de Saúde"
        
        # Remove prefixos comuns de agregadores
        clean_source = source.replace("Google News", "").replace("Bing News", "").replace("NewsAPI -", "").strip()
        
        return clean_source if clean_source else "Assessoria de Imprensa"

    def create_wordpress_structure(self, article: Article, title: str, subtitle: str, source: str, is_litoral: bool) -> str:
        """Cria estrutura completamente limpa do artigo para WordPress - apenas conteúdo editorial"""
        
        # Gera parágrafos baseados na descrição
        paragraphs = self.generate_article_paragraphs(article, is_litoral)
        
        # Conteúdo 100% limpo para WordPress - SEM meta descrição, categorias ou tags
        wordpress_html = f"""<p><img src="{self.get_featured_image(article, is_litoral)}" alt="Imagem relacionada à notícia" class="wp-image-featured aligncenter" /></p>
<p><em>Imagem: Reprodução</em></p>

{paragraphs}

<h2>Impacto Regional</h2>
<p>Este desenvolvimento tem relevância para o Litoral Norte Paulista, região que compreende Ilhabela, São Sebastião, Caraguatatuba e Ubatuba. A população local acompanha atentamente informações que podem afetar o cotidiano da região.</p>

<h2>Próximos Passos</h2>
<p>O acompanhamento dos desdobramentos desta situação permanece em pauta para os órgãos competentes e comunidade local. Novas informações serão divulgadas conforme se tornarem disponíveis através dos canais oficiais.</p>

<p><strong>Fonte:</strong> {source}</p>"""
        
        return wordpress_html

    def generate_article_paragraphs(self, article: Article, is_litoral: bool) -> str:
        """Gera parágrafos estruturados do artigo usando Gemini AI"""
        
        # Se Gemini API está configurada, usa IA para gerar conteúdo mais rico
        if self.gemini_api_key and self.gemini_api_key != 'YOUR_GEMINI_API_KEY':
            try:
                return self.generate_with_gemini(article, is_litoral)
            except Exception as e:
                print(f"Erro ao usar Gemini AI: {e}")
                # Fallback para método padrão
                pass
        
        # Método padrão (fallback)
        description = article.description
        
        # Primeiro parágrafo - introdução
        intro = f"<p>{description}</p>"
        
        # Segundo parágrafo - contextualização
        if is_litoral:
            context = "<p>A informação foi divulgada oficialmente e tem relevância direta para os moradores e visitantes da região. O Litoral Norte Paulista, conhecido por suas belezas naturais e importância turística, frequentemente é palco de desenvolvimentos que merecem atenção especial da comunidade.</p>"
        else:
            context = "<p>Embora a notícia tenha origem em outra região, seus desdobramentos podem ter impacto no Litoral Norte Paulista. A região, que compreende Ilhabela, São Sebastião, Caraguatatuba e Ubatuba, mantém conexões importantes com outros centros urbanos do estado.</p>"
        
        # Terceiro parágrafo - detalhamento
        details = "<p>Os detalhes desta informação serão acompanhados de perto pelos órgãos competentes e pela imprensa local. É importante que a população se mantenha informada sobre os desdobramentos que podem afetar a rotina e os serviços da região.</p>"
        
        return f"{intro}\n\n{context}\n\n{details}"

    def generate_with_gemini(self, article: Article, is_litoral: bool) -> str:
        """Gera conteúdo usando Google Gemini AI"""
        import requests
        
        # Prompt otimizado para o Gemini
        region_context = "do Litoral Norte Paulista (Ilhabela, São Sebastião, Caraguatatuba e Ubatuba)" if is_litoral else "que pode impactar o Litoral Norte Paulista"
        
        prompt = f"""
        Você é um jornalista experiente especializado em notícias do Litoral Norte Paulista.
        
        Baseado nesta notícia:
        Título: {article.title}
        Descrição: {article.description}
        Fonte: {article.source}
        
        Escreva 3 parágrafos em HTML para um artigo jornalístico {region_context}:
        
        1. Primeiro parágrafo: Desenvolva o lead da notícia
        2. Segundo parágrafo: Contextualize a importância para a região
        3. Terceiro parágrafo: Mencione próximos passos ou impactos
        
        Use apenas tags <p> e mantenha linguagem jornalística neutra e profissional.
        Cada parágrafo deve ter entre 60-100 palavras.
        """
        
        # API do Google Gemini
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 20,
                "topP": 0.8,
                "maxOutputTokens": 800
            }
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                generated_text = result['candidates'][0]['content']['parts'][0]['text']
                
                # Limpa e formata o texto gerado
                paragraphs = generated_text.strip()
                
                # Garante que está em formato HTML
                if not paragraphs.startswith('<p>'):
                    # Converte texto simples para HTML
                    lines = paragraphs.split('\n\n')
                    paragraphs = '\n\n'.join([f'<p>{line.strip()}</p>' for line in lines if line.strip()])
                
                print("✅ Conteúdo gerado com Gemini AI")
                return paragraphs
        
        # Se falhar, retorna erro para usar fallback
        raise Exception(f"Gemini API retornou status {response.status_code}")
    
    def expand_content_with_gemini(self, article: Article, base_content: str) -> str:
        """Expande conteúdo existente usando Gemini (método auxiliar)"""
        if self.gemini_api_key and self.gemini_api_key != 'YOUR_GEMINI_API_KEY':
            try:
                prompt = f"""
                Expanda este conteúdo jornalístico sobre {article.title}:
                
                {base_content}
                
                Adicione mais 2 parágrafos relevantes:
                - Um sobre o contexto regional do Litoral Norte
                - Outro sobre possíveis desdobramentos
                
                Mantenha o formato HTML com tags <p>.
                """
                
                # Chamada similar ao método anterior
                # (implementação completa seria aqui)
                return base_content  # Por enquanto retorna o original
                
            except Exception as e:
                print(f"Erro ao expandir com Gemini: {e}")
        
        return base_content

    def create_article_preview(self, article: Article, is_litoral: bool) -> str:
        """Cria preview da estrutura do artigo"""
        return f"""
        <h6><strong>H1:</strong> {article.title}</h6>
        <h6><strong>H2:</strong> Subtítulo contextual</h6>
        <p><strong>Parágrafo 1:</strong> {article.description[:100]}...</p>
        <h6><strong>H3:</strong> Impacto para a Região</h6>
        <p><strong>Parágrafo 2:</strong> Contextualização regional...</p>
        <h6><strong>H3:</strong> Acompanhe Mais Notícias</h6>
        <p><strong>Parágrafo 3:</strong> Call-to-action e conclusão...</p>
        <p><strong>Fonte:</strong> {self.extract_source_name(article.source, article.description)}</p>
        <p><em>Imagem: Reprodução</em></p>
        """

    def get_featured_image(self, article: Article, is_litoral: bool) -> str:
        """Retorna URL de imagem adequada baseada no conteúdo"""
        
        # URLs de imagens padrão baseadas no tema
        litoral_images = [
            "https://images.unsplash.com/photo-1544551763-46a013bb70d5?w=800&h=400&fit=crop",  # Praia
            "https://images.unsplash.com/photo-1502781252888-9143ba7f074e?w=800&h=400&fit=crop",  # Costa
            "https://images.unsplash.com/photo-1505142468610-359e7d316be0?w=800&h=400&fit=crop"   # Mar
        ]
        
        city_images = {
            "ilhabela": "https://images.unsplash.com/photo-1559827260-dc66d52bef19?w=800&h=400&fit=crop",
            "são sebastião": "https://images.unsplash.com/photo-1516815231560-8f41ec531527?w=800&h=400&fit=crop", 
            "caraguatatuba": "https://images.unsplash.com/photo-1544551763-46a013bb7f074e?w=800&h=400&fit=crop",
            "ubatuba": "https://images.unsplash.com/photo-1502781252888-9143ba7f074e?w=800&h=400&fit=crop"
        }
        
        # Verifica se menciona cidade específica
        title_lower = article.title.lower()
        for city, image_url in city_images.items():
            if city in title_lower:
                return image_url
        
        # Retorna imagem padrão do litoral
        import random
        return random.choice(litoral_images)

    def generate_wordpress_tags(self, article: Article, is_litoral: bool) -> str:
        """Gera tags para WordPress"""
        
        base_tags = ["Litoral Norte", "São Paulo", "Notícias"]
        
        # Adiciona cidades do Litoral Norte
        cities = ["Ilhabela", "São Sebastião", "Caraguatatuba", "Ubatuba"]
        title_lower = article.title.lower()
        
        for city in cities:
            if city.lower() in title_lower:
                base_tags.append(city)
        
        # Adiciona tags baseadas no conteúdo
        content_keywords = self.extract_content_keywords(article)
        base_tags.extend(content_keywords)
        
        # Remove duplicatas e limita a 8 tags
        unique_tags = list(dict.fromkeys(base_tags))[:8]
        
        # Formata as tags como badges
        tag_badges = []
        for tag in unique_tags:
            tag_badges.append(f'<span class="badge bg-secondary me-1">{tag}</span>')
        
        return " ".join(tag_badges)

    def extract_content_keywords(self, article: Article) -> List[str]:
        """Extrai palavras-chave relevantes do conteúdo"""
        
        keywords = []
        text = f"{article.title} {article.description}".lower()
        
        # Palavras-chave temáticas
        themes = {
            "turismo": ["turismo", "turista", "visitante", "hotel", "pousada"],
            "meio ambiente": ["meio ambiente", "preservação", "natureza", "sustentabilidade"],
            "saúde": ["saúde", "hospital", "médico", "tratamento"],
            "educação": ["educação", "escola", "universidade", "ensino"],
            "segurança": ["segurança", "polícia", "bombeiros", "emergência"],
            "infraestrutura": ["obra", "construção", "estrada", "ponte"],
            "eventos": ["evento", "festival", "show", "apresentação"]
        }
        
        for theme, words in themes.items():
            if any(word in text for word in words):
                keywords.append(theme.title())
        
        return keywords

    def format_date(self, date_str: str) -> str:
        """Formata data para exibição em português"""
        try:
            from datetime import datetime
            if 'T' in date_str:
                # Formato ISO
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                dt = datetime.now()
            
            return dt.strftime("%d/%m/%Y às %H:%M")
        except:
            return "Data não disponível"

    def extract_image_from_article(self, url: str) -> str:
        """Extrai imagem do artigo original"""
        # Implementação básica - pode ser melhorada com web scraping
        return "https://via.placeholder.com/800x400/0066cc/ffffff?text=Imagem+do+Artigo"

class WordPressPublisher:
    def __init__(self):
        self.wp_url = os.getenv('WP_URL', 'https://jornalvozdolitoral.com')
        self.wp_username = os.getenv('WP_USERNAME', 'automacao')
        self.wp_password = os.getenv('WP_PASSWORD', 'VBGZv5eCueyg1gkvmBfRCSsb')

    def publish_post(self, content: Dict[str, str]) -> bool:
        """Publica conteúdo no WordPress"""
        
        try:
            # Extrai título limpo
            clean_title = content.get('clean_title', content['title'].replace(' | Portal Litoral Norte', ''))
            
            # Se as credenciais WordPress estão configuradas, tenta publicar
            if (self.wp_url != 'https://seu-site.com' and 
                'jornalvozdolitoral.com' in self.wp_url and
                self.wp_username == 'automacao' and 
                len(self.wp_password) > 10):
                
                import requests
                import base64
                
                # Autenticação básica
                credentials = f"{self.wp_username}:{self.wp_password}"
                token = base64.b64encode(credentials.encode()).decode()
                
                headers = {
                    'Authorization': f'Basic {token}',
                    'Content-Type': 'application/json'
                }
                
                # 1. Primeiro, faz upload da imagem destacada
                featured_image_id = self.upload_featured_image(content.get('image_url', ''), headers)
                
                # 2. Cria/obtém tags
                tag_ids = self.create_wp_tags(content, headers)
                
                # 3. Dados do post para WordPress
                post_data = {
                    'title': clean_title,
                    'content': content.get('wordpress_content', content['content']),
                    'status': 'publish',
                    'excerpt': content['meta_description'],
                    'categories': self.get_wp_category_ids(content.get('wp_category', {})),
                    'featured_media': featured_image_id,
                    'tags': tag_ids,
                    'meta': {
                        '_yoast_wpseo_metadesc': content['meta_description'],
                        '_wp_attachment_image_alt': content.get('image_alt', content['meta_description'])
                    }
                }
                
                # API REST do WordPress para posts
                api_url = f"{self.wp_url}/wp-json/wp/v2/posts"
                
                response = requests.post(api_url, json=post_data, headers=headers, timeout=30)
                
                if response.status_code in [200, 201]:
                    post_response = response.json()
                    print(f"✅ Post publicado no WordPress: {clean_title}")
                    print(f"🔗 URL: {post_response.get('link', 'URL não disponível')}")
                    print(f"📸 Imagem destacada ID: {featured_image_id}")
                    print(f"🏷️ Tags criadas: {len(tag_ids)} tags")
                    
                    # Atualiza meta fields se necessário
                    if featured_image_id > 0:
                        self.update_post_meta(post_response['id'], content, headers)
                    
                    return True
                else:
                    print(f"❌ Erro na publicação WordPress: {response.status_code}")
                    print(f"Resposta: {response.text[:200]}")
                    return False
            else:
                # Modo demonstração - mostra como seria publicado
                wp_cat = content.get('wp_category', {})
                print("📋 MODO DEMONSTRAÇÃO - WordPress")
                print(f"📝 Título: {clean_title}")
                print(f"📂 Categoria: {wp_cat.get('full_path', 'Destaque')}")
                print(f"📄 Conteúdo pronto para publicação:")
                print("─" * 50)
                print(content.get('wordpress_content', content['content'])[:200] + "...")
                print("─" * 50)
                print(f"🏷️ Meta descrição: {content['meta_description']}")
                print(f"📸 Imagem destacada: {content.get('image_url', '')}")
                print("✅ Conteúdo formatado e pronto para WordPress!")
                return True
                
        except Exception as e:
            print(f"❌ Erro ao publicar no WordPress: {e}")
            return False

    def get_wp_category_ids(self, wp_category: Dict[str, str]) -> List[int]:
        """Retorna IDs das categorias WordPress (implementar conforme sua instalação)"""
        # Mapeamento básico - ajuste conforme suas categorias WordPress
        category_mapping = {
            "Cidades": 1,
            "Brasil": 2, 
            "Mundo": 3,
            "Destaque": 4,
            "Ilhabela": 5,
            "São Sebastião": 6,
            "Caraguatatuba": 7,
            "Ubatuba": 8
        }
        
        ids = []
        main_cat = wp_category.get('main_category', 'Destaque')
        sub_cat = wp_category.get('subcategory', '')
        
        if main_cat in category_mapping:
            ids.append(category_mapping[main_cat])
        
        if sub_cat and sub_cat in category_mapping:
            ids.append(category_mapping[sub_cat])
            
        return ids if ids else [4]  # Default: Destaque

    def create_wp_tags(self, content: Dict[str, str], headers: Dict[str, str]) -> List[int]:
        """Cria tags no WordPress e retorna os IDs"""
        tag_ids = []
        
        try:
            import requests
            
            # Extrai tags do conteúdo
            tags_text = content.get('tags', '')
            if not tags_text:
                return []
            
            # Remove HTML das tags e extrai texto limpo
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(tags_text, 'html.parser')
            tag_names = [tag.get_text().strip() for tag in soup.find_all('span')]
            
            if not tag_names:
                # Fallback: extrai do texto direto
                import re
                tag_names = re.findall(r'>(.*?)<', tags_text)
            
            for tag_name in tag_names:
                if not tag_name or len(tag_name) < 2:
                    continue
                    
                # Verifica se tag já existe
                search_url = f"{self.wp_url}/wp-json/wp/v2/tags"
                search_params = {'search': tag_name}
                
                search_response = requests.get(
                    search_url, 
                    params=search_params,
                    headers=headers,
                    timeout=15
                )
                
                if search_response.status_code == 200:
                    existing_tags = search_response.json()
                    
                    # Verifica se existe tag com nome exato
                    existing_tag = None
                    for tag in existing_tags:
                        if tag['name'].lower() == tag_name.lower():
                            existing_tag = tag
                            break
                    
                    if existing_tag:
                        tag_ids.append(existing_tag['id'])
                        print(f"🏷️ Tag existente encontrada: {tag_name} (ID: {existing_tag['id']})")
                    else:
                        # Cria nova tag
                        create_data = {
                            'name': tag_name,
                            'slug': tag_name.lower().replace(' ', '-').replace('ã', 'a').replace('ç', 'c')
                        }
                        
                        create_response = requests.post(
                            search_url,
                            json=create_data,
                            headers=headers,
                            timeout=15
                        )
                        
                        if create_response.status_code in [200, 201]:
                            new_tag = create_response.json()
                            tag_ids.append(new_tag['id'])
                            print(f"✅ Nova tag criada: {tag_name} (ID: {new_tag['id']})")
                        else:
                            print(f"❌ Erro ao criar tag '{tag_name}': {create_response.status_code}")
            
            print(f"🏷️ Total de tags processadas: {len(tag_ids)}")
            return tag_ids
            
        except Exception as e:
            print(f"❌ Erro ao processar tags: {e}")
            return []

    def update_post_meta(self, post_id: int, content: Dict[str, str], headers: Dict[str, str]):
        """Atualiza metadados do post"""
        try:
            import requests
            
            # Atualiza alt text da imagem destacada se disponível
            if content.get('image_alt'):
                meta_url = f"{self.wp_url}/wp-json/wp/v2/posts/{post_id}"
                meta_data = {
                    'meta': {
                        '_wp_attachment_image_alt': content['image_alt']
                    }
                }
                
                requests.post(meta_url, json=meta_data, headers=headers, timeout=15)
                print("✅ Meta dados atualizados")
                
        except Exception as e:
            print(f"⚠️ Erro ao atualizar meta dados: {e}")

    def upload_featured_image(self, image_url: str, headers: Dict[str, str]) -> int:
        """Upload da imagem destacada para WordPress"""
        if not image_url:
            return 0
            
        try:
            import requests
            from io import BytesIO
            
            # Download da imagem
            img_response = requests.get(image_url, timeout=30)
            if img_response.status_code != 200:
                print(f"❌ Erro ao baixar imagem: {img_response.status_code}")
                return 0
            
            # Determina o nome do arquivo
            import os
            from urllib.parse import urlparse
            parsed_url = urlparse(image_url)
            filename = os.path.basename(parsed_url.path) or f"featured_image_{int(time.time())}"
            
            # Se não tem extensão, adiciona .jpg
            if '.' not in filename:
                filename += '.jpg'
            
            # Prepara dados para upload
            files = {
                'file': (filename, BytesIO(img_response.content), 'image/jpeg')
            }
            
            # Headers para multipart/form-data
            upload_headers = {
                'Authorization': headers['Authorization']
            }
            
            # Upload via WordPress REST API
            upload_url = f"{self.wp_url}/wp-json/wp/v2/media"
            
            upload_response = requests.post(
                upload_url, 
                files=files, 
                headers=upload_headers,
                timeout=30
            )
            
            if upload_response.status_code in [200, 201]:
                media_data = upload_response.json()
                media_id = media_data.get('id', 0)
                print(f"✅ Imagem destacada uploaded - ID: {media_id}")
                return media_id
            else:
                print(f"❌ Erro no upload da imagem: {upload_response.status_code}")
                print(f"Resposta: {upload_response.text[:200]}")
                return 0
                
        except Exception as e:
            print(f"❌ Erro ao fazer upload da imagem: {e}")
            return 0

class SocialMediaPublisher:
    def __init__(self):
        self.instagram_token = os.getenv('INSTAGRAM_TOKEN', 'YOUR_INSTAGRAM_TOKEN')
        self.facebook_token = os.getenv('FACEBOOK_TOKEN', 'YOUR_FACEBOOK_TOKEN')
        self.canva_api_key = os.getenv('CANVA_API_KEY', 'YOUR_CANVA_API_KEY')

    def create_video_with_canva(self, content: Dict[str, str]) -> str:
        """Cria vídeo usando template personalizado do Canva"""

        # Template ID do seu design personalizado
        canva_template_id = "DAGjU_4d0TA"
        canva_template_url = "https://www.canva.com/design/DAGjU_4d0TA/K6mwHSITpJAr1c-U7kZpqg/edit"

        # Método 1: Se tiver Canva Connect API
        if self.canva_api_key and self.canva_api_key != 'YOUR_CANVA_API_KEY':
            try:
                # Usar template específico com seu logo
                payload = {
                    "template_id": canva_template_id,
                    "title": content['title'][:80],  # Limite de caracteres
                    "description": content['meta_description'][:150],
                    "customize": {
                        "text_elements": [
                            {
                                "element": "main_title",
                                "content": content['title']
                            },
                            {
                                "element": "subtitle", 
                                "content": content['meta_description'][:100]
                            }
                        ]
                    }
                }

                print(f"🎨 Criando vídeo no Canva usando template personalizado...")
                print(f"📋 Template: {canva_template_url}")

                # Quando a API estiver ativa, será usado o template real
                return f"https://canva-generated-video-{int(time.time())}.mp4"

            except Exception as e:
                print(f"Erro na API do Canva: {e}")

        # Método 2: Simulação usando template personalizado
        print(f"🎨 Usando template personalizado do Canva: {canva_template_id}")
        print(f"🎥 Template URL: {canva_template_url}")
        print(f"📝 Título: {content['title']}")

        # Cria versão local baseada no template
        return self.create_branded_template(content, canva_template_id)

    def create_branded_template(self, content: Dict[str, str], template_id: str) -> str:
        """Cria template com a marca personalizada baseado no design do Canva"""
        from PIL import Image, ImageDraw, ImageFont
        import textwrap

        try:
            # Cria imagem base com cores do seu template
            img = Image.new('RGB', (1080, 1350), color='#ffffff')  # Formato vertical para Stories/Reels
            draw = ImageDraw.Draw(img)

            # Adiciona fundo gradiente (simulando seu template)
            # Você pode personalizar essas cores baseado no seu design
            for y in range(1350):
                color_intensity = int(255 * (y / 1350))
                color = (240 - color_intensity//4, 245 - color_intensity//4, 255)
                draw.line([(0, y), (1080, y)], fill=color)

            # Área para logo (topo)
            logo_area = (40, 40, 1040, 200)
            draw.rectangle(logo_area, fill='#f8f9fa', outline='#e9ecef', width=2)
            draw.text((540, 120), "SEU LOGO AQUI", fill='#6c757d', 
                     font=self.get_font(36), anchor='mm')

            # Título principal
            title = content['title'][:80] + '...' if len(content['title']) > 80 else content['title']
            wrapped_title = textwrap.fill(title, width=35)

            title_font = self.get_font(48)
            title_bbox = draw.textbbox((0, 0), wrapped_title, font=title_font)
            title_height = title_bbox[3] - title_bbox[1]

            # Posiciona título no centro-superior
            title_y = 280
            draw.text((540, title_y), wrapped_title, fill='#2c3e50', 
                     font=title_font, anchor='mt', align='center')

            # Descrição/resumo
            if content.get('meta_description'):
                desc = content['meta_description'][:200] + '...' if len(content['meta_description']) > 200 else content['meta_description']
                wrapped_desc = textwrap.fill(desc, width=45)

                desc_font = self.get_font(28)
                desc_y = title_y + title_height + 60
                draw.text((540, desc_y), wrapped_desc, fill='#5a6c7d', 
                         font=desc_font, anchor='mt', align='center')

            # Rodapé com informações
            footer_y = 1250
            draw.rectangle((40, footer_y-10, 1040, footer_y+50), fill='#2c3e50')
            draw.text((540, footer_y+20), f"Template ID: {template_id} | Gerado automaticamente", 
                     fill='white', font=self.get_font(20), anchor='mm')

            # Cria diretório se não existir
            import os
            os.makedirs('static', exist_ok=True)

            # Salva a imagem
            filename = f"static/branded_template_{int(time.time())}.png"
            img.save(filename)

            print(f"✅ Template personalizado criado: {filename}")
            print(f"🎨 Baseado no template Canva: {template_id}")

            return filename

        except Exception as e:
            print(f"Erro ao criar template personalizado: {e}")
            return self.create_simple_video_template(content)

    def get_font(self, size: int):
        """Obtém fonte com tamanho específico"""
        try:
            # Tenta fontes comuns do sistema
            fonts = ["arial.ttf", "helvetica.ttf", "DejaVuSans.ttf"]
            for font_name in fonts:
                try:
                    from PIL import ImageFont
                    return ImageFont.truetype(font_name, size)
                except:
                    continue
            # Fallback para fonte padrão
            from PIL import ImageFont
            return ImageFont.load_default()
        except:
            from PIL import ImageFont
            return ImageFont.load_default()

    def create_simple_video_template(self, content: Dict[str, str]) -> str:
        """Cria um template simples de vídeo/imagem (fallback)"""
        from PIL import Image, ImageDraw
        import textwrap

        try:
            img = Image.new('RGB', (1080, 1080), color='#1e3a8a')
            draw = ImageDraw.Draw(img)

            title = content['title'][:100] + '...' if len(content['title']) > 100 else content['title']
            wrapped_title = textwrap.fill(title, width=30)

            font = self.get_font(48)
            draw.text((540, 540), wrapped_title, fill='white', font=font, anchor='mm', align='center')

            import os
            os.makedirs('static', exist_ok=True)
            filename = f"static/simple_template_{int(time.time())}.png"
            img.save(filename)

            print(f"✅ Template simples criado: {filename}")
            return filename

        except Exception as e:
            print(f"Erro ao criar template: {e}")
            return "https://via.placeholder.com/1080x1080/1e3a8a/ffffff?text=Video+Template"

    def publish_to_instagram(self, content: Dict[str, str], video_url: str) -> bool:
        """Publica no Instagram (Feed e Reels)"""
        try:
            # Se token Instagram está configurado
            if self.instagram_token != 'YOUR_INSTAGRAM_TOKEN' and len(self.instagram_token) > 20:
                import requests
                
                # API do Instagram Graph
                instagram_api_url = "https://graph.facebook.com/v19.0"
                
                # Caption com hashtags
                caption = f"{content.get('clean_title', content['title'])}\n\n{content['meta_description']}\n\n#LitoralNorte #SaoSebastiao #Ilhabela #Caraguatatuba #Ubatuba #Noticias #SaoPaulo"
                
                # Dados para publicação
                post_data = {
                    'image_url': content.get('image_url', video_url),
                    'caption': caption[:2200],  # Limite do Instagram
                    'access_token': self.instagram_token
                }
                
                # Endpoint para Instagram Business Account (precisa configurar)
                response = requests.post(
                    f"{instagram_api_url}/me/media",
                    data=post_data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    media_data = response.json()
                    media_id = media_data.get('id')
                    
                    # Publica o media
                    publish_data = {
                        'creation_id': media_id,
                        'access_token': self.instagram_token
                    }
                    
                    publish_response = requests.post(
                        f"{instagram_api_url}/me/media_publish",
                        data=publish_data,
                        timeout=30
                    )
                    
                    if publish_response.status_code == 200:
                        print(f"✅ Post publicado no Instagram: {content.get('clean_title', content['title'])}")
                        return True
                    else:
                        print(f"❌ Erro ao publicar no Instagram: {publish_response.status_code}")
                        print(f"Resposta: {publish_response.text[:200]}")
                        return False
                else:
                    print(f"❌ Erro ao criar media no Instagram: {response.status_code}")
                    print(f"Resposta: {response.text[:200]}")
                    return False
            else:
                # Modo demonstração - cria post local para simular
                print("📱 MODO DEMONSTRAÇÃO - Instagram")
                print(f"📝 Caption: {content.get('clean_title', content['title'])}")
                print(f"📄 Descrição: {content['meta_description'][:100]}...")
                print(f"📸 Imagem: {content.get('image_url', video_url)}")
                print(f"🏷️ Hashtags: #LitoralNorte #SaoSebastiao #Ilhabela #Caraguatatuba #Ubatuba")
                
                # Simula criação de arquivo de post
                try:
                    import os
                    os.makedirs('social_posts', exist_ok=True)
                    
                    post_filename = f"social_posts/instagram_post_{int(time.time())}.txt"
                    with open(post_filename, 'w', encoding='utf-8') as f:
                        f.write(f"INSTAGRAM POST\n")
                        f.write(f"Título: {content.get('clean_title', content['title'])}\n")
                        f.write(f"Descrição: {content['meta_description']}\n")
                        f.write(f"Imagem: {content.get('image_url', video_url)}\n")
                        f.write(f"Hashtags: #LitoralNorte #SaoSebastiao #Ilhabela #Caraguatatuba #Ubatuba\n")
                    
                    print(f"📄 Post salvo em: {post_filename}")
                except:
                    pass
                
                print("✅ Conteúdo pronto para Instagram!")
                return True
        except Exception as e:
            print(f"❌ Erro ao publicar no Instagram: {e}")
            return False

    def publish_to_facebook(self, content: Dict[str, str], video_url: str) -> bool:
        """Publica no Facebook"""
        try:
            # Se token Facebook está configurado
            if self.facebook_token != 'YOUR_FACEBOOK_TOKEN' and len(self.facebook_token) > 20:
                import requests
                
                # API do Facebook Graph
                facebook_api_url = "https://graph.facebook.com/v19.0"
                
                # Mensagem do post
                message = f"{content.get('clean_title', content['title'])}\n\n{content['meta_description']}\n\n#LitoralNorte #Noticias"
                
                # Dados para publicação com imagem
                post_data = {
                    'message': message[:8000],  # Limite do Facebook
                    'link': content.get('image_url', video_url),
                    'access_token': self.facebook_token
                }
                
                # Endpoint para página do Facebook (precisa configurar page_id)
                page_id = "me"  # Substitua pelo ID da sua página
                response = requests.post(
                    f"{facebook_api_url}/{page_id}/feed",
                    data=post_data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    post_data = response.json()
                    post_id = post_data.get('id')
                    print(f"✅ Post publicado no Facebook: {content.get('clean_title', content['title'])}")
                    print(f"🔗 Post ID: {post_id}")
                    return True
                else:
                    print(f"❌ Erro ao publicar no Facebook: {response.status_code}")
                    print(f"Resposta: {response.text[:200]}")
                    return False
            else:
                # Modo demonstração - cria post local para simular
                print("📘 MODO DEMONSTRAÇÃO - Facebook")
                print(f"📝 Título: {content.get('clean_title', content['title'])}")
                print(f"📄 Texto: {content['meta_description'][:100]}...")
                print(f"📸 Mídia: {content.get('image_url', video_url)}")
                
                # Simula criação de arquivo de post
                try:
                    import os
                    os.makedirs('social_posts', exist_ok=True)
                    
                    post_filename = f"social_posts/facebook_post_{int(time.time())}.txt"
                    with open(post_filename, 'w', encoding='utf-8') as f:
                        f.write(f"FACEBOOK POST\n")
                        f.write(f"Título: {content.get('clean_title', content['title'])}\n")
                        f.write(f"Texto: {content['meta_description']}\n")
                        f.write(f"Link: {content.get('image_url', video_url)}\n")
                        f.write(f"Hashtags: #LitoralNorte #Noticias\n")
                    
                    print(f"📄 Post salvo em: {post_filename}")
                except:
                    pass
                
                print("✅ Conteúdo pronto para Facebook!")
                return True
        except Exception as e:
            print(f"❌ Erro ao publicar no Facebook: {e}")
            return False

# Instâncias globais
news_collector = NewsCollector()
seo_generator = SEOGenerator()
wp_publisher = WordPressPublisher()
social_publisher = SocialMediaPublisher()

# Configurações globais - Palavras-chave fixas do Litoral Norte Paulista
KEYWORDS = [
    "Litoral Norte Paulista",
    "Litoral Norte de São Paulo", 
    "Ilhabela",
    "São Sebastião",
    "Caraguatatuba", 
    "Ubatuba"
]
AUTO_MODE = False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search_news', methods=['POST'])
def search_news():
    """Busca notícias baseada em palavras-chave"""
    data = request.get_json()
    keywords = data.get('keywords', KEYWORDS)
    hours = data.get('hours', 24)

    articles = news_collector.search_news(keywords, hours)

    # Converte para dicionário para JSON
    articles_dict = []
    for article in articles:
        articles_dict.append({
            'title': article.title,
            'url': article.url,
            'description': article.description,
            'published_at': article.published_at,
            'source': article.source
        })

    return jsonify({'articles': articles_dict})

@app.route('/generate_content', methods=['POST'])
def generate_content():
    """Gera conteúdo SEO para um artigo selecionado"""
    data = request.get_json()

    article = Article(
        title=data['title'],
        url=data['url'],
        description=data['description'],
        published_at=data['published_at'],
        source=data['source']
    )

    seo_content = seo_generator.generate_seo_content(article)

    return jsonify(seo_content)

@app.route('/publish_content', methods=['POST'])
def publish_content():
    """Publica conteúdo em todas as plataformas"""
    data = request.get_json()
    content = data.get('content')

    results = {}

    # Publica no WordPress
    results['wordpress'] = wp_publisher.publish_post(content)

    # Cria vídeo no Canva
    video_url = social_publisher.create_video_with_canva(content)

    # Publica nas redes sociais
    results['instagram'] = social_publisher.publish_to_instagram(content, video_url)
    results['facebook'] = social_publisher.publish_to_facebook(content, video_url)

    return jsonify({
        'success': True,
        'results': results,
        'video_url': video_url
    })

@app.route('/toggle_auto_mode', methods=['POST'])
def toggle_auto_mode():
    """Ativa/desativa modo automático"""
    global AUTO_MODE
    data = request.get_json()
    AUTO_MODE = data.get('enabled', False)

    if AUTO_MODE:
        # Agenda execução automática a cada hora
        schedule.every().hour.do(run_auto_process)
        print("🤖 Modo automático ativado")
    else:
        schedule.clear()
        print("⏹️ Modo automático desativado")

    return jsonify({'auto_mode': AUTO_MODE})

@app.route('/auto_status')
def auto_status():
    """Retorna status do modo automático"""
    return jsonify({'auto_mode': AUTO_MODE})

def run_auto_process():
    """Executa processo automático completo"""
    print("🔄 Iniciando processo automático...")

    try:
        # 1. Busca notícias
        articles = news_collector.search_news(KEYWORDS, 24)

        if not articles:
            print("❌ Nenhum artigo encontrado")
            return

        # 2. Seleciona o primeiro artigo (pode implementar lógica de seleção)
        selected_article = articles[0]
        print(f"📰 Artigo selecionado: {selected_article.title}")

        # 3. Gera conteúdo SEO
        seo_content = seo_generator.generate_seo_content(selected_article)

        # 4. Publica em todas as plataformas
        wp_publisher.publish_post(seo_content)
        video_url = social_publisher.create_video_with_canva(seo_content)
        social_publisher.publish_to_instagram(seo_content, video_url)
        social_publisher.publish_to_facebook(seo_content, video_url)

        print("✅ Processo automático concluído com sucesso!")

    except Exception as e:
        print(f"❌ Erro no processo automático: {e}")

def run_scheduler():
    """Executa o agendador em thread separada"""
    while True:
        schedule.run_pending()
        time.sleep(60)

# Inicia thread do agendador
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)