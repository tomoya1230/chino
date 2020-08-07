# coding: utf-8

import asyncio
import functools
import itertools
import math
import random
import sys
import time

import discord
import youtube_dl
from async_timeout import timeout
from discord.ext import commands

youtube_dl.utils.bug_reports_message = lambda: ''

class VoiceError(Exception):
    pass


class YTDLError(Exception):
    pass


class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',
        'source_address': '0.0.0.0',
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn',
    }

    ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)

    def __init__(self, ctx: commands.Context, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data

        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        date = data.get('upload_date')
        self.upload_date = date[6:8] + '.' + date[4:6] + '.' + date[0:4]
        self.title = data.get('title')
        self.thumbnail = data.get('thumbnail')
        self.description = data.get('description')
        self.duration = self.parse_duration(int(data.get('duration')))
        self.tags = data.get('tags')
        self.url = data.get('webpage_url')
        self.views = data.get('view_count')
        self.likes = data.get('like_count')
        self.dislikes = data.get('dislike_count')
        self.stream_url = data.get('url')

    def __str__(self):
        return '**{0.title}**'.format(self)

    @classmethod
    async def create_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError('`{}`の検索結果が見つかりませんでした'.format(search))

        if 'entries' not in data:
            process_info = data
        else:
            process_info = None
            for entry in data['entries']:
                if entry:
                    process_info = entry
                    break

            if process_info is None:
                raise YTDLError('`{}`の検索結果が見つかりませんでした'.format(search))

        webpage_url = process_info['webpage_url']
        partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError('Couldn\'t fetch `{}`'.format(webpage_url))

        if 'entries' not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info['entries'].pop(0)
                except IndexError:
                    raise YTDLError('Couldn\'t retrieve any matches for `{}`'.format(webpage_url))
        
        return cls(ctx, discord.FFmpegPCMAudio(info['url'], **cls.FFMPEG_OPTIONS), data=info)

    @classmethod
    async def search_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        channel = ctx.channel
        loop = loop or asyncio.get_event_loop()

        cls.search_query = '%s%s:%s' % ('ytsearch', 10, ''.join(search))

        partial = functools.partial(cls.ytdl.extract_info, cls.search_query, download=False, process=False)
        info = await loop.run_in_executor(None, partial)

        cls.search = {}
        cls.search["title"] = f'検索結果:\n**{search}**'
        cls.search["type"] = 'rich'
        cls.search["color"] = 16761035
        cls.search["author"] = {'name': f'{ctx.author.name}', 'url': f'{ctx.author.avatar_url}', 'icon_url': f'{ctx.author.avatar_url}'}
        
        lst = []

        for e in info['entries']:
            VId = e.get('id')
            VUrl = 'https://www.youtube.com/watch?v=%s' % (VId)
            lst.append(f'`{info["entries"].index(e) + 1}.` [{e.get("title")}]({VUrl})\n')

        lst.append('\n**番号を入力してください, キャンセルの場合は『cancel』と入力してください**')
        cls.search["description"] = "\n".join(lst)

        em = discord.Embed.from_dict(cls.search)
        await ctx.send(embed=em, delete_after=45.0)

        def check(msg):
            return msg.content.isdigit() == True and msg.channel == channel or msg.content == 'cancel' or msg.content == 'Cancel'
        
        try:
            m = await bot.wait_for('message', check=check, timeout=45.0)

        except asyncio.TimeoutError:
            rtrn = 'timeout'

        else:
            if m.content.isdigit() == True:
                sel = int(m.content)
                if 0 < sel <= 10:
                    for key, value in info.items():
                        if key == 'entries':
                            """data = value[sel - 1]"""
                            VId = value[sel - 1]['id']
                            VUrl = 'https://www.youtube.com/watch?v=%s' % (VId)
                            partial = functools.partial(cls.ytdl.extract_info, VUrl, download=False)
                            data = await loop.run_in_executor(None, partial)
                    rtrn = cls(ctx, discord.FFmpegPCMAudio(data['url'], **cls.FFMPEG_OPTIONS), data=data)
                else:
                    rtrn = 'sel_invalid'
            elif m.content == 'cancel':
                rtrn = 'cancel'
            else:
                rtrn = 'sel_invalid'
        
        return rtrn

    @staticmethod
    def parse_duration(duration: int):
        if duration > 0:
            minutes, seconds = divmod(duration, 60)
            hours, minutes = divmod(minutes, 60)
            days, hours = divmod(hours, 24)

            duration = []
            if days > 0:
                duration.append('{}'.format(days))
            if hours > 0:
                duration.append('{}'.format(hours))
            if minutes > 0:
                duration.append('{}'.format(minutes))
            if seconds > 0:
                duration.append('{}'.format(seconds))
            
            value = ':'.join(duration)
        
        elif duration == 0:
            value = "LIVE"
        
        return value


class Song:
    __slots__ = ('source', 'requester')

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester
    
    def create_embed(self):
        embed = (discord.Embed(title='再生中', description='```css\n{0.source.title}\n```'.format(self), color=discord.Color.blurple())
                .add_field(name='再生時間', value=self.source.duration)
                .add_field(name='URL', value='[youtube]({0.source.url})'.format(self))
                .set_thumbnail(url=self.source.thumbnail)
                .set_author(name=self.requester.name, icon_url=self.requester.avatar_url))
        return embed


class SongQueue(asyncio.Queue):
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        del self._queue[index]


class VoiceState:
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx

        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()
        self.exists = True

        self._loop = False
        self._volume = 0.5
        self.skip_votes = set()

        self.audio_player = bot.loop.create_task(self.audio_player_task())

    def __del__(self):
        self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value

    @property
    def is_playing(self):
        return self.voice and self.current

    async def audio_player_task(self):
        while True:
            self.next.clear()
            self.now = None

            if self.loop == False:
                try:
                    async with timeout(180):  
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    self.bot.loop.create_task(self.stop())
                    self.exists = False
                    return
                
                self.current.source.volume = self._volume
                self.voice.play(self.current.source, after=self.play_next_song)
                await self.current.source.channel.send(embed=self.current.create_embed())
                
            elif self.loop == True:
                self.now = discord.FFmpegPCMAudio(self.current.source.stream_url, **YTDLSource.FFMPEG_OPTIONS)
                self.voice.play(self.now, after=self.play_next_song)
            
            await self.next.wait()

    def play_next_song(self, error=None):
        if error:
            raise VoiceError(str(error))

        self.next.set()

    def skip(self):
        self.skip_votes.clear()

        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()

        if self.voice:
            await self.voice.disconnect()
            self.voice = None


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if not state or not state.exists:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state

        return state

    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage('このコマンドはDMでは使用できません')

        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await ctx.send('E: {}'.format(str(error)))

    @commands.command(name='join', invoke_without_subcommand=True)
    async def _join(self, ctx: commands.Context):

        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='summon')
    @commands.has_permissions(manage_guild=True)
    async def _summon(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):

        if not channel and not ctx.author.voice:
            raise VoiceError('You are neither connected to a voice channel nor specified a channel to join.')

        destination = channel or ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='leave', aliases=['disconnect'])
    @commands.has_permissions(manage_guild=True)
    async def _leave(self, ctx: commands.Context):

        if not ctx.voice_state.voice:
            return await ctx.send('ボイスチャンネルに接続していません')

        await ctx.voice_state.stop()
        await ctx.send('ボイスチャンネルから切断しました')
        del self.voice_states[ctx.guild.id]

    @commands.command(name='volume')
    @commands.is_owner()
    async def _volume(self, ctx: commands.Context, *, volume: int):

        if not ctx.voice_state.is_playing:
            return await ctx.send('今は何も再生していませんよ')

        if 0 > volume > 100:
            return await ctx.send('ボリュームは0から100でお願いします')

        ctx.voice_state.volume = volume / 100
        await ctx.send('{}%に設定しました'.format(volume))

    @commands.command(name='now', aliases=['current', 'playing'])
    async def _now(self, ctx: commands.Context):
        embed = ctx.voice_state.current.create_embed()
        await ctx.send(embed=embed)

    @commands.command(name='pause', aliases=['pa'])
    @commands.has_permissions(manage_guild=True)
    async def _pause(self, ctx: commands.Context):
        if ctx.voice_state.is_playing and ctx.voice_state.voice.is_playing():
            ctx.voice_state.voice.pause()
            await ctx.message.add_reaction('⏯')

    @commands.command(name='resume', aliases=['re', 'res'])
    @commands.has_permissions(manage_guild=True)
    async def _resume(self, ctx: commands.Context):

        if ctx.voice_state.is_playing and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction('⏯')

    @commands.command(name='stop')
    @commands.has_permissions(manage_guild=True)
    async def _stop(self, ctx: commands.Context):

        ctx.voice_state.songs.clear()

        if ctx.voice_state.is_playing:
            ctx.voice_state.voice.stop()
            await ctx.message.add_reaction('⏹')

    @commands.command(name='skip', aliases=['s'])
    async def _skip(self, ctx: commands.Context):

        if not ctx.voice_state.is_playing:
            return await ctx.send('今は何も再生していませんよ')

        voter = ctx.message.author
        if voter == ctx.voice_state.current.requester:
            await ctx.message.add_reaction('⏭')
            ctx.voice_state.skip()

        elif voter.id not in ctx.voice_state.skip_votes:
            ctx.voice_state.skip_votes.add(voter.id)
            total_votes = len(ctx.voice_state.skip_votes)

            if total_votes >= 3:
                await ctx.message.add_reaction('⏭')
                ctx.voice_state.skip()
            else:
                await ctx.send('スキップ投票　**{}/3**票'.format(total_votes))

        else:
            await ctx.send('あなたは既にスキップに投票していますよ')

    @commands.command(name='queue', aliases=['q'])
    async def _queue(self, ctx: commands.Context, *, page: int = 1):

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('キューが空っぽです')

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ''
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):
            queue += '`{0}.` [{1.source.title}]({1.source.url})\n'.format(i + 1, song)

        embed = (discord.Embed(description='キュー　　**{}曲**\n\n{}'.format(len(ctx.voice_state.songs), queue))
                 .set_footer(text='{}/{}ページ'.format(page, pages)))
        await ctx.send(embed=embed)

    @commands.command(name='shuffle')
    async def _shuffle(self, ctx: commands.Context):

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('キューが空っぽです')

        ctx.voice_state.songs.shuffle()
        await ctx.message.add_reaction('✅')

    @commands.command(name='remove')
    async def _remove(self, ctx: commands.Context, index: int):

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('キューが空っぽです')

        ctx.voice_state.songs.remove(index - 1)
        await ctx.message.add_reaction('✅')

    @commands.command(name='loop', aliases=['l'])
    async def _loop(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send('今は何も再生していませんよ')
        ctx.voice_state.loop = not ctx.voice_state.loop
        await ctx.message.add_reaction('✅')

    @commands.command(name='play', aliases=['p'])
    async def _play(self, ctx: commands.Context, *, search: str):

        async with ctx.typing():
            try:
                source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop)
            except YTDLError as e:
                await ctx.send('{}の処理中にエラーが発生しました'.format(str(e)))
            else:
                if not ctx.voice_state.voice:
                    await ctx.invoke(self._join)

                song = Song(source)
                await ctx.voice_state.songs.put(song)
                await ctx.send('{}をキューに追加しました'.format(str(source)))

    @commands.command(name='search')
    async def _search(self, ctx: commands.Context, *, search: str):
        async with ctx.typing():
            try:
                source = await YTDLSource.search_source(ctx, search, loop=self.bot.loop)
            except YTDLError as e:
                await ctx.send('{}の処理中にエラーが発生しました'.format(str(e)))
            else:
                if source == 'sel_invalid':
                    await ctx.send('Invalid selection')
                elif source == 'cancel':
                    await ctx.send(':white_check_mark:')
                elif source == 'timeout':
                    await ctx.send(':alarm_clock: **Time\'s up bud**')
                else:
                    if not ctx.voice_state.voice:
                        await ctx.invoke(self._join)

                    song = Song(source)
                    await ctx.voice_state.songs.put(song)
                    await ctx.send('{}をキューに追加しました'.format(str(source)))
            
    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError('先にボイスチャンネルに入ってくださいね')

        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError('私は既にボイスチャンネルに接続していますよ')

bot = commands.Bot(command_prefix='=', case_insensitive=True)
bot.add_cog(Music(bot))
bot.remove_command('help')


@bot.event
async def on_ready():
    print('Logged in as {0} ({0.id})'.format(bot.user))
    print('===============================')
    print('Ⅱ  ■■■  ■   ■ ■■■ ■   ■  ■■■  Ⅱ')
    print('Ⅱ ■   ■ ■   ■  ■  ■■  ■ ■   ■ Ⅱ')
    print('Ⅱ ■     ■■■■■  ■  ■ ■ ■ ■   ■ Ⅱ')
    print('Ⅱ ■   ■ ■   ■  ■  ■  ■■ ■   ■ Ⅱ')
    print('Ⅱ  ■■■  ■   ■ ■■■ ■   ■  ■■■  Ⅱ')
    print('=============================== tomoya’s discord.bot')
    await bot.change_presence(activity=discord.Game(name="チノちゃんver3.1"))

@bot.command()
async def logout(ctx): 
    if ctx.author.id == 651753103539961895:
        await ctx.send("ログアウトします")
        await bot.logout()
        await sys.exit()
    else:
        reply = f'すみません、{ctx.author.mention}さん\nこのコマンドの実行権限を持っているのは\ntomoya12302#7187さんだけなんです'
        await ctx.send(reply)
        return
    
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if bot.user in message.mentions :
    	await message.channel.send('呼びましたか?\nコマンドは『!』で始めてくださいね')
    if message.content == 'チノちゃん愛してる':
    	if message.author.id == 651753103539961895:
    		reply = f'私も {message.author.mention} さんを愛しています'
    		await message.channel.send(reply)
    	else:
    		reply = f'ありがとうございます {message.author.mention} さん'
    		await message.channel.send(reply)
    if message.content == 'チノちゃん誰が好き？':
        if message.author.id == 651753103539961895:
            reply = f'もちろん {message.author.mention} さんです'
            await message.channel.send(reply)
        else:
            reply = f'内緒です'
            await message.channel.send(reply)
    else:
        await bot.process_commands(message)
        return
    	
@bot.command()
async def chino(ctx):
	messages = ["本気でバリスタ目指したいなら、\nコーヒーの違いくらい当ててみてください。", "今日のところは…これくらいにしといて…\nあげます…ガクッ…。", "わたしは木の役を積極的にやりました。\n木はいいです。不動のあり方は心があらわれます。","ココアさんにとってわたしは\n我が子を谷に突き落とすライオンです。\n\n這い上がって来た時に\n笑顔の写真を撮らせてあげるんです、多分。","こんな事までして…\nココアさんは本当にしょうがないココアさんです","わ…わたしはバリスタを目指すんです！\n画家にはなりませんよ！","わたしにもシャボン玉の作り方を教えてください。","わ…わたしおいしくないです！食べないでください！やめてください！","今日から抹茶派です。コーヒー派に宣戦布告です。","とっておきのボトルシップ…\nお休みの今日にふさわしい相手ですね…","あ！願い事…！\nまたみんなで…みんなで遊べますように！\n\nあの…願い事言えたら叶うって本で読んだことが…\nわたしだけ…？","がおー！食っちまうぞー！","香風智乃です。\n将来の夢は立派なバリスタです。","ココアさんがいかに甘い考えか証明してみせます！","これがバリスタの力…！","お話…　一緒に寝る…\n私にちゃんと出来るかな…","これからおじいちゃんを焼きます","大変です！\nココアさんがケチャップで死んでます！","ティッピーが頭に乗ってたら2倍の力が出せるんです\nうそじゃないです","…お姉ちゃんの　ねぼすけ","今の私の方がすき…？","苦しいんですか！？\n私にできることがあったら何でも言ってください！","たくさん食べて、たくさん寝て、\n最低でもココアさんよりは大きくなります","ココアさん。\n私に華麗なる顔面レシーブを見せて下さい！","今日は何だか落ち着きません。\nまだ、お話していたい気分です"]
	await ctx.send(random.choice(messages))
    
@bot.command()
async def help(ctx):
	
	await ctx.send("お困りですか？\n詳細は、私を作ってくれた\n`@tomoya12302#7187`さんに聞けば早いと思いますが\n簡単な機能を一覧で表示しますね\n```!play :曲をキューに追加し、再生します\n!queue:キューのリスト表示\n!skip :曲をスキップします\n!leave:ボイスチャンネルから切断します(管理者権限)```")
	
@bot.command(name='info', aliases=['i'])
async def info(ctx):
    embed = discord.Embed(title='チノちゃんver3.1', description='DiscordMusicBOT')
    embed.set_thumbnail(url='https://encrypted-tbn0.gstatic.com/images?q=tbn%3AANd9GcQoi7PfqWFRcBF0pqVawVl-eQ8fH_YwJ0xK1Q&usqp=CAU')
    embed.add_field(name='更新内容', value='・漫画配布マネージ機能追加\n・プリフィックスの変更(=)\n・機能修正')
    embed.add_field(name='開発者', value='Discord：@tomoya12302#7187\nTwitter ：[@tomoya12302](https://twitter.com/tomoya12302?s=09)')
    await ctx.send(embed=embed)
    
@bot.command(pass_context=True)
async def ping(ctx):
    message = await ctx.send('測定中…')
    await asyncio.sleep(1)
    await message.edit(content=f'{round(bot.latency * 1000)}ms')

@bot.command()
async def manga(ctx):
    embed1 = discord.Embed(title="以下の項目から番号を入力してください",description="1：在庫にある漫画からダウンロード\n2：仕入れリクエスト\n3：キャンセル")
    await ctx.send(embed=embed1, delete_after=45.0)
    y = ctx.author.id
    def check2(msg):
        return msg.content.isdigit() == True
    try:
        m = await bot.wait_for('message', check=check2, timeout=45.0)
        if m.content.isdigit() == True:
            if m.content == '1' and m.author.id == y:
                embed1 = discord.Embed(title="漫画を選んでください",description="1：かぐや様は告らせたい\n2：からかい上手の(元)高木さん\n3：五等分の花嫁\n4：小林さんちのメイドラゴン\n5：源君物語(エロ本)\n6：約束のネバーランド\n7：鬼滅の刃\n8：賭ケグルイ\n9：からかい上手の高木さん\n10：監獄学園\n11：モンスター娘のいる日常(エロ本)\n12：ご注文はうさぎですか？\n13：転生したらスライムだった件\n14：spy×family(寄せ集め)\n15：将来的に死んでくれ\n16：ダーリン・イン・ザ・フランキス\n17：がっこうぐらし！(怖いかも)\n18：日常\n19：ダンまち\n20：防振り\n21：ワンパンマン\n22：聲の形\n23:ジョジョの奇妙な冒険\n0：↩メニューへ戻る")
                await ctx.send(embed=embed1, delete_after=45.0)
                while m.author.id == y:
                    def check3(msg):
                	    return msg.content.isdigit() == True
                    time.sleep(1.5)
                    m = await bot.wait_for('message', check=check3, timeout=60.0)
                    sel2 = int(m.content)
                    if m.content == '0':
                        await manga(ctx)
                        return
                    elif m.content == '1':
                        x = "かぐや様は告らせたい"
                        break
                    elif m.content == '2':
                        x = "からかい上手の(元)高木さん"
                        break
                    elif m.content == '3':
                        x = "五等分の花嫁"
                        break
                    elif m.content == '4':
                        x = "小林さんちのメイドラゴン"
                        break
                    elif m.content == '5':
                        x = "源君物語"
                        break
                    elif m.content == '6':
                        x = "約束のネバーランド"
                        break
                    elif m.content == '7':
                        x = "鬼滅の刃"
                        break
                    elif m.content == '8':
                        x = "賭ケグルイ"
                        break
                    elif m.content == '9':
                        x = "からかい上手の高木さん"
                        break
                    elif m.content == '10':
                        x = "監獄学園"
                        break
                    elif m.content == '11':
                        x = "モンスター娘のいる日常"
                        break
                    elif m.content == '12':
                        x = "ご注文はうさぎですか？"
                        break
                    elif m.content == '13':
                        x = "転生したらスライムだった件"
                        break
                    elif m.content == '14':
                        x = "spy×family"
                        break
                    elif m.content == '15':
                        x = "将来的に死んでくれ"
                        break
                    elif m.content == '16':
                        x = "ダーリン・イン・ザ・フランキス"
                        break
                    elif m.content == '17':
                        x = "がっこうぐらし！"
                        break
                    elif m.content == '18':
                        x = "日常"
                        break
                    elif m.content == '19':
                        x = "ダンまち"
                        break
                    elif m.content == '20':
                        x = "防振り"
                        break
                    elif m.content == '21':
                        x = "ワンパンマン"
                        break
                    elif m.content == '22':
                        x = "聲の形"
                        break
                    elif m.content == '23':
                        x = "ジョジョの奇妙な冒険"
                        break
                    elif not 0 <= sel2 < 24:
                        await ctx.send("入力が間違っていますよ\nもう一度数字を入力してください", delete_after=45.0)
                user = bot.get_user(651753103539961895)
                await ctx.send("`@tomoya12302#7187`さんに送信しました\n対応するまで待っててください")
                ri = m.author
                await user.send('`{}`さんが'.format(str(ri)))
                await user.send('『{}』のダウンロードを希望しました'.format(str(x)))
                return
            elif m.content == '3' and m.author.id == y:
                await ctx.send("キャンセルされました")
                return
            elif m.content == '2' and m.author.id == y:
                def check4(msg):
                	return msg.content.isdigit() == False
                await ctx.send("漫画の名前を入力してください\n(戻る場合は『back』と入力してください)", delete_after=45.0)
                time.sleep(1.5)
                m = await bot.wait_for('message', check=check4, timeout=60.0)
                if m.content == 'back' and m.author.id == y:
                    await manga(ctx)
                    return
                elif m.author.id == y:
                    user = bot.get_user(651753103539961895)
                    await ctx.send("`@tomoya12302#7187`さんに送信しました\n対応するまで待っててください")
                    ri = m.author
                    await user.send('`{}`さんが'.format(str(ri)))
                    await user.send('『{}』を入荷希望しました'.format(str(m.content)))
            elif m.author.id == y:
                await ctx.send("入力が間違っていますよ", delete_after=45.0)
                await manga(ctx)
                return
    except asyncio.TimeoutError:
        rtrn = 'timeout'

@bot.command()
async def newka(ctx, new):
    if ctx.author.bot:
        return
    elif ctx.author.id == 651753103539961895:
        mc = bot.get_channel(739812746161291374)
        await mc.send('『{}』が入荷しました'.format(str(new)))
        return
    else:
        return
bot.run('NjU1Mzg2NDkzOTYyOTQ0NTEy.XwaFnQ.p9K_TROWN8PJH3bym0kIZ-T75CY')