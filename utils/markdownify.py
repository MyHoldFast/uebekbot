from bs4 import BeautifulSoup, NavigableString, Tag
import re

re_newline = re.compile(r'\r\n?')
re_html_heading = re.compile(r'h(\d+)')
re_make_convert_fn_name = re.compile(r'[\[\]:-]')
re_backtick_runs = re.compile(r'`+')

ASTERISK='*'
STRIP_ONE='strip_one'
UNDERLINED='underlined'

def strip1_pre(t):
    return re.sub(r'\n *$','',re.sub(r'^ *\n','',t))

def chomp(t):
    p=' ' if t and t[0]==' ' else ''
    s=' ' if t and t[-1]==' ' else ''
    return p,s,t.strip()

def abstract_inline_conversion(fn):
    def impl(self,el,text,parent_tags):
        m=fn(self)
        ms='</'+m[1:] if m.startswith('<') and m.endswith('>') else m
        if '_noformat' in parent_tags: 
            return text
        p,s,text=chomp(text)
        if not text: 
            return ''
        return f'{p}{m}{text}{ms}{s}'
    return impl

def _todict(o):
    return {k:getattr(o,k) for k in dir(o) if not k.startswith('_')}

class MarkdownConverter:
    class DefaultOptions:
        autolinks=True
        bs4_options='html.parser'
        escape_asterisks=True
        escape_underscores=True
        heading_style=UNDERLINED
        preserve_leading_spaces=True
        strip_pre=STRIP_ONE
        strong_em_symbol=ASTERISK

    class Options(DefaultOptions):
        pass

    def __init__(self,**options):
        self.options=_todict(self.DefaultOptions)
        self.options.update(_todict(self.Options))
        self.options.update(options)
        bs4=self.options['bs4_options']
        if not isinstance(bs4,dict):
            bs4={'features':bs4}
        bs4['preserve_whitespace_tags']=['pre','code']
        self.options['bs4_options']=bs4
        self.convert_fn_cache={}

    def convert(self,html):
        soup=BeautifulSoup(html,**self.options['bs4_options'])
        return self.convert_soup(soup)

    def convert_soup(self,soup):
        return self.process_tag(soup,set())

    def process_element(self,node,parent_tags):
        if isinstance(node,NavigableString):
            return self.process_text(node,parent_tags)
        return self.process_tag(node,parent_tags)

    def process_tag(self,node,parent_tags):
        parent_tags=set(parent_tags)
        parent_tags.add(node.name)
        out=[]
        for c in node.children:
            if isinstance(c,(Tag,NavigableString)):
                out.append(self.process_element(c,parent_tags))
        text=''.join(x for x in out if x)
        fn=self.get_conv_fn_cached(node.name)
        return fn(node,text,parent_tags) if fn else text

    def process_text(self,el,parent_tags):
        text=str(el)
        if 'pre' not in parent_tags and 'code' not in parent_tags:
            text=re_newline.sub('\n',text)
        if '_noformat' not in parent_tags:
            if self.options['escape_asterisks']:
                text=text.replace('*','\\*')
            if self.options['escape_underscores']:
                text=text.replace('_','\\_')
        return text

    def get_conv_fn_cached(self,name):
        if name not in self.convert_fn_cache:
            self.convert_fn_cache[name]=self.get_conv_fn(name)
        return self.convert_fn_cache[name]

    def get_conv_fn(self,tag):
        tag=tag.lower()
        fn=getattr(self,f'convert_{re_make_convert_fn_name.sub("_",tag)}',None)
        if fn:
            return fn
        m=re_html_heading.match(tag)
        if m:
            return lambda el,t,p:self.convert_hN(int(m.group(1)),el,t,p)

    convert_b=abstract_inline_conversion(lambda s:2*s.options['strong_em_symbol'])
    convert_em=abstract_inline_conversion(lambda s:s.options['strong_em_symbol'])
    convert_strong=convert_b

    def convert_p(self,el,text,parent_tags):
        return f'\n\n{text.rstrip()}\n\n'

    def convert_pre(self,el,text,parent_tags):
        if self.options['strip_pre']==STRIP_ONE:
            text=strip1_pre(text)
        return f'\n\n```\n{text}\n```\n\n'

    def convert_code(self,el,text,parent_tags):
        p,s,text=chomp(text)
        if not text:
            return ''
        m=max((len(x) for x in re.findall(re_backtick_runs,text)),default=0)
        d='`'*(m+1)
        if m>0:
            text=f' {text} '
        return f'{p}{d}{text}{d}{s}'

    def convert_hN(self,n,el,text,parent_tags):
        n=min(6,max(1,n))
        return f'\n\n{"#"*n} {text.strip()}\n\n'

def markdownify(html,**options):
    return MarkdownConverter(**options).convert(html)
