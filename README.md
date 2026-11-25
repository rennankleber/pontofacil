# PontoFácil

Sistema web de controle de ponto desenvolvido como Projeto de Conclusão de Curso.

## Tecnologias
- Python
- Flask
- SQLite
- Flask-SQLAlchemy
- Flask-Login
- Bootstrap 5

## Requisitos
Python 3.10 ou superior.

## Como executar

1. Clone o repositório:
   ```bash
   git clone URL_DO_SEU_REPOSITORIO
   cd pontofacil
   ```

2. Crie e ative um ambiente virtual:
   ```bash
   python -m venv .venv
   ```
   Windows:
   ```bash
   .venv\\Scripts\\activate
   ```
   macOS/Linux:
   ```bash
   source .venv/bin/activate
   ```

3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

4. Execute:
   ```bash
   python run.py
   ```

5. Acesse http://127.0.0.1:5000

No Windows, também é possível iniciar o servidor e abrir o navegador com dois cliques em `iniciar_pontofacil.bat`.

Para desenvolvimento com recarga automática, defina `FLASK_DEBUG=1`. O sistema usa
`America/Sao_Paulo` como fuso horário por padrão; ajuste `TIMEZONE` se necessário.
Defina `SECRET_KEY` com um valor secreto estável antes de implantar o sistema.
Na primeira inicialização, uma senha temporária do dono do sistema é gerada e
mostrada no terminal; altere-a após entrar. O e-mail padrão é
`dono@pontofacil.local`. É possível configurar `INITIAL_OWNER_EMAIL` e
`INITIAL_OWNER_PASSWORD` antes da primeira execução.

O dono cadastra empresas e seus administradores em `/dono`. O cadastro da
empresa inclui nome, telefone e CNPJ. Administradores e funcionários têm
cadastro com nome completo, CPF, data de nascimento, e-mail, matrícula,
departamento e cargo; o e-mail e a senha inicial são usados para entrar no
sistema. Na edição, a senha pode ser redefinida e fica vazia por padrão para
preservar a atual. Na lista de empresas, o dono abre uma empresa para gerenciar
seus administradores e funcionários. Nesse contexto, pode cadastrar, editar e
desativar funcionários, consultar relatórios e corrigir marcações; as correções
mantêm justificativa e auditoria identificada com o usuário que as realizou.
Cada administrador continua restrito à própria empresa. Ao atualizar um banco
existente, os registros atuais são preservados e associados à empresa
`Empresa migrada`; os novos dados de perfil ficam vazios até serem preenchidos.

O menu Suporte oferece conversas entre funcionários e os administradores da
empresa, e entre cada administrador e o dono. As mensagens ficam salvas e são
atualizadas automaticamente a cada cinco segundos.

## Testes

```bash
python -m unittest discover -s tests
```

## Primeiro acesso (ambiente local)
- Dono: `dono@pontofacil.local`
- Senha temporária: exibida no terminal na primeira inicialização

## Estrutura
- `app/models.py`: modelos e tabelas do banco.
- `app/routes/`: rotas da aplicação, incluindo o painel do dono e o isolamento por empresa.
- `app/templates/`: páginas HTML.
- `app/static/`: CSS, JavaScript e imagens.
- `instance/`: banco SQLite local (não versionado).

O arquivo `instance/pontofacil_esquema.db` é uma cópia segura de referência, com as tabelas vazias. O banco local com dados permanece ignorado pelo Git.

## Observações
Este é o ponto de partida do projeto acadêmico. Foram adicionados testes básicos,
fuso horário configurável e auditoria de correções. Antes de qualquer uso real
como sistema de ponto, ainda são necessários testes mais abrangentes, regras de
jornada completas, revisão de segurança e análise dos requisitos legais aplicáveis.

Correções de marcações feitas pelo administrador exigem justificativa e mantêm um
histórico de valores anteriores e novos. A tabela de auditoria é criada
automaticamente sem alterar as marcações existentes.

A exclusão de funcionários é uma exclusão lógica. O registro permanece no banco,
é desativado e perde o acesso ao sistema para preservar o histórico de marcações
e permitir uma reativação posterior.
