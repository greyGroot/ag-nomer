# **Розробка інтелектуального PWA-застосунку для СТО: Архітектура, технології та алгоритми комп'ютерного зору**

## **Концептуальна архітектура та технологічна стратегія**

Сучасні станції технічного обслуговування (СТО) потребують радикальної оптимізації процесів прийому автомобілів, де швидкість та точність фіксації транспортного засобу безпосередньо впливають на операційну ефективність. Традиційний процес передбачає ручне введення номерних знаків, кольору та часу прибуття, що створює ризики людської помилки та затримує обслуговування. Автоматизація цього процесу за допомогою камери смартфона дозволяє миттєво ідентифікувати автомобіль, його візуальні характеристики, а також точний час прибуття.  
Найкращим архітектурним рішенням для реалізації такого продукту є створення Progressive Web App (PWA). Використання PWA забезпечує кросплатформність, відсутність необхідності тривалого процесу розгортання через магазини застосунків (App Store, Google Play), а також можливість стабільної роботи в умовах нестабільного інтернет-з'єднання, що є типовою проблемою для виробничих приміщень СТО з великою кількістю металевих конструкцій, які екранують сигнал.  
Архітектура розроблюваної системи базується на парадигмі розподілених обчислень і поділяється на два ключові логічні блоки. Клієнтська частина (Edge/Frontend) функціонує у браузері мобільного пристрою як PWA, відповідаючи за захоплення відеопотоку, вилучення оптимальних кадрів, локальне кешування та асинхронну синхронізацію даних1. Серверна частина (Cloud/Backend) реалізується як набір високопродуктивних мікросервісів, що використовують архітектури глибокого навчання (Deep Learning) для детекції об'єктів, сегментації, класифікації кольору та оптичного розпізнавання символів (OCR) номерних знаків, адаптованих під український та європейський формати2.

## **Клієнтська інфраструктура: PWA, WebRTC та офлайн-синхронізація**

Реалізація клієнтської частини вимагає вирішення трьох фундаментальних інженерних завдань: отримання безпечного доступу до необхідного апаратного забезпечення пристрою, вилучення високоякісних кадрів без ефекту розмиття та забезпечення безперебійної роботи у зонах без доступу до мережі Інтернет.

### **Управління медіа-потоками та API камери**

Основним інтерфейсом для взаємодії з камерою у веб\-середовищі є метод navigator.mediaDevices.getUserMedia(), який функціонує виключно у безпечних контекстах (HTTPS або localhost)6. Оскільки застосунок призначений для використання технічним персоналом СТО, які фотографують автомобілі, необхідно гарантовано активувати основну (тилову) камеру пристрою.  
Специфікація WebRTC дозволяє керувати вибором камери за допомогою об'єкта MediaStreamConstraints та параметра facingMode8. Щоб уникнути активації фронтальної камери, архітектура застосунку повинна використовувати строге обмеження exact:

JavaScript  
const constraints \= {  
  audio: false,  
  video: {   
    facingMode: { exact: "environment" },  
    width: { ideal: 1920 },  
    height: { ideal: 1080 }  
  }  
};

Використання ключового слова ideal для параметрів роздільної здатності є критично важливим архітектурним рішенням. Алгоритми браузера намагаються знайти налаштування камери з найменшою дистанцією відхилення від ідеальних значень6. Якщо розробник вкаже жорсткі параметри (наприклад, exact: 1920), а пристрій не підтримує таку роздільну здатність апаратно, проміс буде відхилено з помилкою OverconstrainedError, що призведе до неможливості використання застосунку6. Роздільна здатність 1080p є оптимальною для даної задачі: вона надає достатньо піксельної щільності для нейронних мереж, які розпізнають дрібні символи номерних знаків, і водночас не перевантажує мережевий канал передачі даних, як це відбувалося б у випадку з 4K-відео.  
У сценаріях, коли мобільний пристрій має декілька тилових камер (наприклад, ширококутна, макро, телефото), використання лише facingMode може бути недостатнім, оскільки браузер може обрати неоптимальний об'єктив. У таких випадках застосовується метод mediaDevices.enumerateDevices(), який повертає масив усіх доступних медіа-пристроїв. Аналізуючи властивість label (наприклад, шукаючи ключові слова "back" або "environment"), система може отримати точний deviceId потрібної камери та передати його у getUserMedia9.

### **Синхронне захоплення кадрів**

Передача безперервного відеопотоку на серверну частину є вкрай неефективною з точки зору використання пропускної здатності мережі та обчислювальних ресурсів сервера. Натомість PWA-застосунок має вилучати окремі високоякісні кадри (фрейми) та надсилати їх як зображення. Традиційний підхід веб\-розробки з використанням функції setInterval для копіювання кадру на елемент \<canvas\> є апаратно незалежним, що часто призводить до десинхронізації з частотою оновлення екрана пристрою і, як наслідок, захоплення розмитих або неповних кадрів.  
Сучасним інженерним стандартом є використання API requestVideoFrameCallback()11. Цей метод дозволяє синхронізувати операції малювання відеокадру на елементі \<canvas\> із частотою оновлення (v-sync) браузера. Зворотний виклик (callback) спрацьовує саме тоді, коли новий кадр з камери готовий до відображення на екрані. Це гарантує захоплення найчіткішого можливого зображення без розмиття в русі (motion blur), що є критичним фактором для успішного спрацьовування OCR-моделі на наступних етапах. Крім того, цей API надає точні метадані, включаючи receiveTime, що дозволяє максимально точно зафіксувати мілісекунду створення знімка11.

### **Офлайн-архітектура та фонова синхронізація**

Виробничі зони СТО часто характеризуються наявністю "сліпих зон" Wi-Fi через масивні металеві перекриття та обладнання. Якщо застосунок потребуватиме постійного інтернет-з'єднання для роботи, його впровадження буде неуспішним. Архітектура PWA вирішує цю проблему за допомогою Service Workers, Cache API та IndexedDB1.  
Процес управління даними в умовах перебоїв зі зв'язком має такий вигляд:

> 1. Застосунок кешує всі власні статичні ресурси під час першого завантаження, що дозволяє інтерфейсу відкриватися миттєво навіть без підключення до мережі.  
> 2. Під час фотографування автомобіля, бінарні дані зображення (перетворені через canvas.toBlob()) разом із метаданими (локальний час пристрою, ідентифікатор сесії) зберігаються у браузерній базі даних IndexedDB1.  
> 3. Відбувається виклик Background Sync API шляхом реєстрації події синхронізації: SyncManager.register('sync-cars')1.  
> 4. Щойно операційна система мобільного пристрою фіксує відновлення стабільного з'єднання з інтернетом, Service Worker автоматично ініціює фонову відправку збережених в IndexedDB зображень на сервер, навіть якщо сам застосунок вже був закритий користувачем або згорнутий у фоновий режим1.

| Стан мережі | Збереження зображення | Обробка на сервері | Дії інтерфейсу користувача |
| :---- | :---- | :---- | :---- |
| **Онлайн (Online)** | Оперативна пам'ять \-\> Мережа | Негайна (бл. 1-2 сек) | Відображення результату (JSON) |
| **Офлайн (Offline)** | IndexedDB | Відкладена | Індикація збереження, очікування |
| **Відновлення (Sync)** | Читання з IndexedDB \-\> Мережа | Фактична обробка | Фонове повідомлення про успіх |

Цей механізм гарантує, що жоден клієнтський автомобіль не буде втрачено з бази даних через тимчасову відсутність зв'язку.

## **Детекція транспортних засобів: Алгоритми локалізації**

Після передачі зображення на серверну частину, першим завданням конвеєра комп'ютерного зору (Computer Vision Pipeline) є знаходження самого автомобіля на фотографії. Застосування алгоритмів детекції дозволяє відкинути фоновий шум (будівлі, людей, обладнання СТО) і сфокусувати подальші обчислювальні ресурси виключно на релевантній області.  
Для цього завдання індустріальним стандартом є використання нейромережевої архітектури YOLO (You Only Look Once). Історично для подібних завдань використовувалися моделі YOLOv3 або YOLOv4, які демонстрували непогану швидкість, але потребували значних обчислювальних ресурсів для досягнення високої точності5. Сучасні рішення переходять на використання YOLOv8 або YOLO11 від Ultralytics, які забезпечують безпрецедентну точність при виявленні автомобілів навіть у складних умовах (часткове перекриття, погане освітлення, інтенсивний рух)15.  
Архітектура YOLO базується на згорткових нейронних мережах (CNN), таких як ResNet-50 або CSPDarknet, які виступають у ролі екстракторів ознак (feature extractors)5. Мережа ділить вхідне зображення на логічну сітку та одночасно передбачає координати обмежувальних рамок (bounding boxes) і ймовірності належності об'єкта до певного класу (наприклад, sedan, SUV, truck, bus) для кожної клітинки5.  
Оскільки YOLO часто генерує кілька обмежувальних рамок для одного і того ж автомобіля, на виході мережі застосовується алгоритм Non-Maximum Suppression (NMS). NMS аналізує метрику Intersection Over Union (IOU) між рамками та залишає лише ту, яка має найвищий рівень впевненості (confidence threshold), відкидаючи дублікати12. Якщо система оброблятиме відеопотік (а не окремі кадри), YOLOv11 може бути доповнено алгоритмами трекінгу, такими як ByteTrack або BoT-SORT, що дозволяє присвоювати унікальні ідентифікатори автомобілям у кадрі та зменшувати навантаження на систему розпізнавання15.  
Після успішної детекції координати рамки \[x\_min, y\_min, x\_max, y\_max\] використовуються для обрізання (cropping) зображення. З цього моменту подальший аналіз кольору та номерних знаків відбувається виключно всередині цієї обрізаної області, що суттєво підвищує загальну продуктивність системи.

## **Класифікація кольору: Від пікселів до людського сприйняття**

Визначення кольору автомобіля є одним із найскладніших завдань комп'ютерного зору, незважаючи на гадану простоту. Складність полягає у тому, що фотографії на СТО робляться в неконтрольованих умовах: вплив яскравого сонця, глибоких тіней, бруду на кузові, а також відблисків від лакофарбового покриття суттєво спотворюють реальний колір автомобіля на фотографії17.

### **Недоліки RGB та необхідність сегментації**

Найпростіший підхід — обчислення середнього значення пікселів у просторі RGB для області обмежувальної рамки — є в корені помилковим. По-перше, прямокутна рамка включає асфальт, вікна автомобіля, шини та фонові об'єкти, які спотворять середній колір. По-друге, тінь на червоному автомобілі може мати значення RGB \[40, 0, 0\], що алгоритмічно ближче до чорного \[0, 0, 0\], ніж до еталонного червоного \[255, 0, 0\]17.  
Для вирішення першої проблеми необхідно використовувати моделі сегментації екземплярів (Instance Segmentation), наприклад, YOLO-Seg. Замість прямокутної рамки ця модель генерує полігональну маску, яка точно повторює контури кузова автомобіля, виключаючи вікна та колеса19. Лише пікселі, що потрапляють у цю маску, беруться до аналізу.  
Для фільтрації тіней та відблисків пікселі маски тимчасово переводяться у колірний простір HSV (Hue, Saturation, Value)21. Завдяки цьому можна відфільтрувати пікселі з надзвичайно низькою яскравістю (тіні) або надзвичайно високою (відблиски сонця), а також пікселі з нульовою насиченістю (сірі елементи, бруд) за допомогою порогових значень (thresholding)21. Решта пікселів кластеризується за допомогою алгоритму K-means для знаходження домінуючого кольору кузова17.

### **Колірний простір CIE LAB та метрика Delta E**

Для порівняння знайденого домінуючого кольору з базовою палітрою кольорів СТО (Білий, Чорний, Сріблястий, Червоний, Синій, Зелений тощо) простір RGB є непридатним, оскільки він не є перцептивно однорідним. Це означає, що однакова математична відстань між двома точками в RGB може не відповідати візуальній різниці, яку сприймає людське око18.  
Рішенням є використання колірного простору CIE LAB, який розроблений для математичної апроксимації людського зору. У цьому просторі ![][image1] відповідає за світлоту (Lightness), ![][image2] — за положення між червоним та зеленим, а ![][image3] — за положення між жовтим та синім кольорами22.  
Для обчислення різниці між кольором автомобіля та еталонними кольорами палітри використовується метрика Delta E (![][image4]). Початкова формула 1976 року (![][image5]) була простою евклідовою відстанню у просторі LAB, але вона мала недоліки при роботі з насиченими кольорами. Тому індустріальним стандартом на сьогодні є застосування складнішої, але значно точнішої формули CIEDE2000 (![][image6]), яка компенсує нелінійність людського сприйняття в області синіх та сірих відтінків18.  
У мові програмування Python розрахунок CIEDE2000 можна легко імплементувати за допомогою спеціалізованих бібліотек, таких як python-colormath (функція delta\_e\_cie2000) або scikit-image (метод skimage.color.deltaE\_ciede2000)18. Алгоритм обчислює значення ![][image4] між домінуючим кольором та всіма кольорами палітри, і обирає той колір, для якого це значення є мінімальним.

| Значення Delta E (ΔE) | Сприйняття кольорової різниці людським оком |
| :---- | :---- |
| **\<= 1.0** | Непомітна різниця (кольори виглядають ідентичними) |
| **1.0 \- 2.0** | Дуже мала різниця, помітна лише уважному спостерігачу |
| **2.0 \- 10.0** | Помітна різниця, але кольори належать до одного відтінку |
| **\> 10.0** | Кольори сприймаються як абсолютно різні |

Завдяки впровадженню метрики Delta E, система здатна класифікувати темно-бордовий автомобіль у тіні саме як "Червоний", а не "Чорний", що відповідає логіці оператора СТО.

## **Оптичне розпізнавання номерних знаків (ALPR/ANPR)**

Визначення номерного знака є найбільш критичною функцією системи для ідентифікації клієнта. Розробка систем Automatic License Plate Recognition (ALPR) супроводжується значними викликами через розмаїття форматів номерів, шрифтів, кутів зйомки та умов освітлення.

### **Порівняльний аналіз ALPR-рушіїв**

Ринок пропонує декілька відкритих та комерційних рішень для ALPR. Традиційні системи, такі як OpenALPR (написані мовою C++), широко використовувалися для створення прототипів, однак вони базуються на застарілих моделях і часто демонструють зниження точності на нестандартних або кириличних форматах номерних знаків26. Комерційні рішення, як-от Plate Recognizer або Anyline, пропонують високу точність та хмарну інтеграцію, але вимагають ліцензійних відрахувань за кожен розпізнаний номер, що масштабує витрати бізнесу27.  
Для розв'язання задачі розпізнавання як українських, так і загальноєвропейських номерних знаків найбільш адаптованим та потужним інструментом є екосистема **Nomeroff Net**2. Цей відкритий фреймворк (GNU GPL v3), розроблений компанією RIA.com, спеціально тренувався на базі даних AUTO.RIA Numberplate Dataset, яка містить величезну вибірку номерних знаків східноєвропейського регіону4.

| ALPR Рішення | Тип ліцензії | Підтримка форматів України / ЄС | Архітектура OCR | Особливості розгортання |
| :---- | :---- | :---- | :---- | :---- |
| **OpenALPR** | Open-source (Legacy) | Базова (потребує тюнінгу) | Tesseract / LBP | On-premise, C++ / Python26 |
| **Plate Recognizer** | Комерційна (SaaS) | Висока | Власна закрита | Cloud API / Docker27 |
| **Eyedea** | Комерційна | Висока | Власна (MobileNet) | Cloud / Edge SDK28 |
| **Nomeroff Net** | Open-source (GPLv3) | Найвища для Східної Європи | GRU (RNN) | On-premise, Python, Docker4 |

### **Архітектура конвеєра Nomeroff Net**

Робота з Nomeroff Net організована у вигляді послідовного конвеєра обробки (pipeline), що складається з чотирьох основних етапів.  
**1\. Локалізація та пошук ключових точок (Numberplate Detection)**  
На першому етапі використовується спеціалізована модель на базі YOLO (починаючи з версії 4.0.0 фреймворк підтримує архітектури YOLOv8 та YOLOv11)4. Відмінність цієї моделі полягає у тому, що вона натренована знаходити не лише обмежувальну рамку (bbox) навколо номера, але й ідентифікувати 4 ключові точки (кути) номерного знака в межах цієї рамки29.  
**2\. Корекція перспективи (Perspective Transformation)**  
Оскільки оператор СТО часто фотографує автомобіль під кутом (збоку або зблизька), номерний знак на двовимірному зображенні виглядає як трапеція, що унеможливлює коректну роботу класифікатора символів. Використовуючи координати 4-х точок, система ініціює механізм корекції перспективного спотворення (активується параметром fixGeometry \= true)29. За допомогою математичних перетворень матриці (наприклад, через OpenCV) зображення номера деформується таким чином, щоб він став ідеально прямокутним, ніби сфотографованим строго фронтально.  
**3\. Класифікація регіону та формату (Options Classification)**  
Вирівняний номер передається до класифікатора, який базується на згортковій нейронній мережі (в останніх версіях використовується бекбоун efficientnet\_v2\_s або спрощені CNN-архітектури)29. Ця мережа виконує категоризацію за один прохід із точністю понад 99,9%29. Ключовою перевагою Nomeroff Net для заявленого завдання є глибока деталізація українських форматів: замість загальної ідентифікації "Україна", система розрізняє дизайни різних періодів видачі, такі як eu\_ua\_1995 (з українським прапором зліва), eu\_ua\_2004 (з жовто-блакитним фоном) та eu\_ua\_2015 (з синьою смугою європейського зразка)2. Для інших європейських країн, якщо їх локальні класифікатори не дотреновані окремо, номер позначається загальним класом eu2.  
**4\. Оптичне розпізнавання символів (OCR)**  
Найскладніший етап перетворення візуальних контурів на текст виконується за допомогою рекурентних нейронних мереж (RNN). У ранніх версіях систем розпізнавання популярним було використання Tesseract, проте його архітектура погано працює зі специфічними шрифтами номерів. Nomeroff Net замінив Tesseract на спеціалізовану нейромережу із GRU-шарами (Gated Recurrent Unit), яка натренована на специфічних датасетах (AUTO.RIA Numberplate OCR UA Dataset, AUTO.RIA Numberplate OCR EU Dataset)4. RNN ідеально підходять для OCR, оскільки вони здатні аналізувати послідовність символів, враховуючи контекст, що допомагає системі відрізняти літеру "O" від цифри "0" на основі формату номера конкретної країни.

## **Серверна інфраструктура та оптимізація продуктивності**

Перенесення моделей глибокого навчання (YOLO, EfficientNet, GRU) на клієнтську сторону (через TensorFlow.js)31 технічно можливе, але для даного комплексного пайплайну це призведе до значного перегріву мобільних пристроїв, швидкого розряду батареї та повільної роботи на бюджетних смартфонах. Тому обчислювальне навантаження переноситься на серверну інфраструктуру.

### **Технологічний стек бекенду**

Для реалізації продуктивного API використовується фреймворк FastAPI (Python). FastAPI є індустріальним стандартом для ML-мікросервісів завдяки нативній підтримці асинхронного програмування (asyncio), що дозволяє обробляти велику кількість паралельних запитів (наприклад, у моменти пікових навантажень на СТО вранці), не блокуючи головний потік при очікуванні відповіді від відеокарт13.  
Комп'ютерний зір реалізується на базі PyTorch та OpenCV (обробка матриць зображень, перетворення колірних просторів). Для розгортання системи застосовується контейнеризація за допомогою Docker. Nomeroff Net надає готові Dockerfile як для роботи на центральних процесорах (CPU), так і з підтримкою апаратного прискорення на графічних картах (GPU)29.

### **Апаратне прискорення та TensorRT**

Для досягнення затримки (latency) інференсу менше ніж 1 секунда на одне зображення3, наявність серверної відеокарти NVIDIA (або пристроїв edge-обчислень типу Jetson) є обов'язковою33.  
Оскільки базові моделі Nomeroff-Net та YOLO у форматі PyTorch/TensorFlow споживають значний обсяг оперативної пам'яті, їх розгортання в умовах обмежених ресурсів потребує оптимізації33. Інженерним рішенням є компіляція моделей у формат TensorRT, розроблений NVIDIA для максимізації швидкості інференсу. Процес включає конвертацію вихідної моделі у проміжний формат ONNX (Open Neural Network Exchange), з якого потім створюється оптимізований рушій TensorRT, адаптований під конкретну архітектуру GPU33. Це забезпечує максимальну пропускну здатність конвеєра при масовій фотофіксації автомобілів.

## **Структурування даних: Формування результуючого JSON**

Останнім етапом процесу є консолідація результатів детекції та метаданих в єдиний стандартизований формат JSON для подальшої інтеграції з ERP або CRM системами СТО.  
Важливим архітектурним нюансом є синхронізація часу. Оскільки PWA може відправляти дані з затримкою через офлайн-режим (Background Sync API)1, час фіксації (capture\_datetime) повинен генеруватися на стороні клієнта у момент натискання кнопки зйомки і передаватися на сервер разом із зображенням, а не встановлюватися сервером у момент отримання запиту.  
Результуюча структура JSON має бути ієрархічною, розширюваною та містити метрики впевненості (confidence scores) для кожної нейромережі. Це дозволяє логіці CRM-системи СТО приймати рішення: якщо впевненість OCR низька, система може підсвітити номер червоним кольором і попросити оператора підтвердити його вручну.  
Приклад ідеальної архітектури JSON-об'єкта для даного завдання:

JSON  
{  
  "transaction\_id": "550e8400-e29b-41d4-a716-446655440000",  
  "metadata": {  
    "capture\_datetime": "2026-08-18T18:12:00+03:00",  
    "sync\_status": "delayed\_background\_sync",  
    "client\_device": {  
      "user\_agent": "Mozilla/5.0 (Linux; Android 13; SM-S918B)...",  
      "camera\_facing": "environment",  
      "resolution": "1920x1080"  
    },  
    "processing\_time\_ms": 845  
  },  
  "results": {  
    "vehicle": {  
      "detected": true,  
      "bounding\_box": \[31, 273, 401, 467\],  
      "detection\_confidence": 0.998,  
      "color": {  
        "name\_en": "black",  
        "name\_ua": "чорний",  
        "delta\_e\_score": 2.45  
      }  
    },  
    "license\_plate": {  
      "detected": true,  
      "number": "KA1234AB",  
      "region": {  
        "country": "ua",  
        "type": "eu\_ua\_2015"  
      },  
      "ocr\_confidence": 0.985  
    }  
  }  
}

### **Словник даних JSON-об'єкта**

| Поле JSON | Тип | Опис та механізм формування |
| :---- | :---- | :---- |
| transaction\_id | UUID | Унікальний ідентифікатор події, генерується клієнтом для відстеження дублікатів під час перебоїв зв'язку. |
| capture\_datetime | ISO 8601 | Локальний час пристрою на момент створення знімка, забезпечує точність хронометражу незалежно від стану мережі. |
| vehicle.color | Об'єкт | Визначається шляхом конвертації YOLO-маски в CIE LAB та обчислення мінімального Delta E (CIEDE2000) до еталонних кольорів18. |
| delta\_e\_score | Float | Метрика перцептивної різниці. Значення \< 2.0 означає майже ідеальний збіг з еталонним кольором СТО. |
| region.type | Рядок | Класифікатор Nomeroff Net (EfficientNet). Демонструє здатність розрізняти періоди видачі (наприклад, 2015 рік) для України29. |
| ocr\_confidence | Float | Рівень впевненості GRU-мережі у розпізнаному тексті номера29. Використовується для ручної валідації. |

Наведена архітектура створює відмовостійкий, високоточний та масштабований програмний комплекс, який задовольняє всі потреби сучасної СТО. Комбінація клієнтських веб\-технологій (WebRTC, Service Workers, Background Sync)1 та сучасних архітектур комп'ютерного зору (YOLOv11 для детекції, CIEDE2000 для кольору, GRU для OCR номерних знаків)15 забезпечує безперебійне автоматизоване розпізнавання транспортних засобів та глибоку інтеграцію з обліковими системами підприємства.

#### **Джерела**

> 1. Make Your PWA Work Offline Part 2 \- Dynamic Data \- Monterail, [https://www.monterail.com/blog/pwa-offline-dynamic-data](https://www.monterail.com/blog/pwa-offline-dynamic-data)  
> 2. EU \- per country detection · Issue \#318 · ria-com/nomeroff-net \- GitHub, [https://github.com/ria-com/nomeroff-net/issues/318](https://github.com/ria-com/nomeroff-net/issues/318)  
> 3. ANPR for Reading Car Plates \- Smart and Advanced Automatic Number Plate Recognition API \- AI.RIA.COM, [https://ai.ria.com/en/numplate-riader](https://ai.ria.com/en/numplate-riader)  
> 4. Nomeroff Net. Automatic numberplate recognition system from AUTO.RIA.com. Version 0.2.3, [https://nomeroff.net.ua/](https://nomeroff.net.ua/)  
> 5. (PDF) Deep Learning-Based Vehicle Type and Color Classification to Support Safe Autonomous Driving \- ResearchGate, [https://www.researchgate.net/publication/378332461\_Deep\_Learning-Based\_Vehicle\_Type\_and\_Color\_Classification\_to\_Support\_Safe\_Autonomous\_Driving](https://www.researchgate.net/publication/378332461_Deep_Learning-Based_Vehicle_Type_and_Color_Classification_to_Support_Safe_Autonomous_Driving)  
> 6. MediaDevices: getUserMedia() method \- Web APIs | MDN, [https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)  
> 7. MediaDevices.getUserMedia() \- Интерфейсы веб API \- MDN Web Docs, [https://developer.mozilla.org/ru/docs/Web/API/MediaDevices/getUserMedia](https://developer.mozilla.org/ru/docs/Web/API/MediaDevices/getUserMedia)  
> 8. getUserMedia() Video Constraints \- Deconstruct \- A Blog From the Makers of Pipe, [https://blog.addpipe.com/getusermedia-video-constraints/](https://blog.addpipe.com/getusermedia-video-constraints/)  
> 9. javascript \- GetUserMedia \- facingmode \- Stack Overflow, [https://stackoverflow.com/questions/32086122/getusermedia-facingmode](https://stackoverflow.com/questions/32086122/getusermedia-facingmode)  
> 10. HTML userMedia facingMode: "environment"doesn't work on android phone, [https://stackoverflow.com/questions/64553141/html-usermedia-facingmode-environmentdoesnt-work-on-android-phone](https://stackoverflow.com/questions/64553141/html-usermedia-facingmode-environmentdoesnt-work-on-android-phone)  
> 11. HTMLVideoElement.requestVideoFrameCallback() \- GitHub Pages, [https://wicg.github.io/video-rvfc/](https://wicg.github.io/video-rvfc/)  
> 12. benaloha/car-classifier-yolo3-python: Car color classification with YOLOv3 object detector, [https://github.com/benaloha/car-classifier-yolo3-python](https://github.com/benaloha/car-classifier-yolo3-python)  
> 13. Vehicle Recognition API \- brand and color classification · GitHub, [https://github.com/benaloha/vehicle-recognition-api](https://github.com/benaloha/vehicle-recognition-api)  
> 14. Deep Learning-Based Vehicle Type and Color Classification to Support Safe Autonomous Driving \- MDPI, [https://www.mdpi.com/2076-3417/14/4/1600](https://www.mdpi.com/2076-3417/14/4/1600)  
> 15. Better Vehicle Re-Identification With Ultralytics YOLO Models, [https://www.ultralytics.com/blog/enhancing-vehicle-re-identification-with-ultralytics-yolo-models](https://www.ultralytics.com/blog/enhancing-vehicle-re-identification-with-ultralytics-yolo-models)  
> 16. Vehicle Counting, Classification & Detection using OpenCV & Python \- TechVidvan, [https://techvidvan.com/tutorials/opencv-vehicle-detection-classification-counting/](https://techvidvan.com/tutorials/opencv-vehicle-detection-classification-counting/)  
> 17. What is a good way to extract dominant colors from image without the shadow?, [https://stackoverflow.com/questions/36894358/what-is-a-good-way-to-extract-dominant-colors-from-image-without-the-shadow](https://stackoverflow.com/questions/36894358/what-is-a-good-way-to-extract-dominant-colors-from-image-without-the-shadow)  
> 18. Difference Between 2 Colours Using Python \- DEV Community, [https://dev.to/tejeshreddy/color-difference-between-2-colours-using-python-182b](https://dev.to/tejeshreddy/color-difference-between-2-colours-using-python-182b)  
> 19. SAM segmentation masks to YOLO format · ultralytics · Discussion \#6421 \- GitHub, [https://github.com/orgs/ultralytics/discussions/6421](https://github.com/orgs/ultralytics/discussions/6421)  
> 20. How to segment multiple objects with YOLO Python \- Eran Feit, [https://eranfeit.net/how-to-segment-multiple-objects-with-yolo-python/](https://eranfeit.net/how-to-segment-multiple-objects-with-yolo-python/)  
> 21. Scikit-Image, Numpy, and Selecting Colors (python) \- Signal Processing Stack Exchange, [https://dsp.stackexchange.com/questions/36223/scikit-image-numpy-and-selecting-colors-python](https://dsp.stackexchange.com/questions/36223/scikit-image-numpy-and-selecting-colors-python)  
> 22. Color segmentation by Delta E color difference \- File Exchange \- MATLAB Central, [https://www.mathworks.com/matlabcentral/fileexchange/31118-color-segmentation-by-delta-e-color-difference](https://www.mathworks.com/matlabcentral/fileexchange/31118-color-segmentation-by-delta-e-color-difference)  
> 23. Delta E Equations — python-colormath 3.0.0 documentation \- Read the Docs, [https://python-colormath.readthedocs.io/en/latest/delta\_e.html](https://python-colormath.readthedocs.io/en/latest/delta_e.html)  
> 24. skimage.color — skimage 0.26.0 documentation, [https://scikit-image.org/docs/stable/api/skimage.color.html](https://scikit-image.org/docs/stable/api/skimage.color.html)  
> 25. python-colormath/doc\_src/delta\_e.rst at master \- GitHub, [https://github.com/gtaylor/python-colormath/blob/master/doc\_src/delta\_e.rst](https://github.com/gtaylor/python-colormath/blob/master/doc_src/delta_e.rst)  
> 26. openalpr/openalpr: Automatic License Plate Recognition library \- GitHub, [https://github.com/openalpr/openalpr](https://github.com/openalpr/openalpr)  
> 27. Top 10 ALPR Software Solutions (2026 Update) \- Plate Recognizer, [https://platerecognizer.com/top-10-alpr-software-solutions/](https://platerecognizer.com/top-10-alpr-software-solutions/)  
> 28. ANPR / ALPR Software – Number Plate Reader \- Eyedea Recognition, [https://www.eyedea.ai/products/number-plate-reading-anpr](https://www.eyedea.ai/products/number-plate-reading-anpr)  
> 29. nomeroff-net/History.md at master \- GitHub, [https://github.com/ria-com/nomeroff-net/blob/master/History.md](https://github.com/ria-com/nomeroff-net/blob/master/History.md)  
> 30. Nomeroff Net \- Циклопедия, [https://cyclowiki.org/wiki/Nomeroff\_Net](https://cyclowiki.org/wiki/Nomeroff_Net)  
> 31. Export YOLO26 to TensorFlow.js (TF.js) \- Ultralytics YOLO, [https://docs.ultralytics.com/integrations/tfjs](https://docs.ultralytics.com/integrations/tfjs)  
> 32. rm-yakovenko/nomeroff-net-docker: NomeroffNet REST API \- GitHub, [https://github.com/rm-yakovenko/nomeroff-net-docker](https://github.com/rm-yakovenko/nomeroff-net-docker)  
> 33. Разработка производительного распознавателя автономеров для edge-устройств, [https://habr.com/ru/articles/797275/](https://habr.com/ru/articles/797275/)  
> 34. GitHub \- AnnaVeller/detect-license-plates-python, [https://github.com/AnnaVeller/detect-license-plates-python](https://github.com/AnnaVeller/detect-license-plates-python)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA4AAAAaCAYAAACHD21cAAAAqUlEQVR4XmNgGHmAA4gF0AWBgAddAB2AFEgC8Vsg/g/E5lA+yECiwG8GiEaSAAsDRNNzdAlCQIQBonErugQhkA7E/4DYBV0CHwA5cw0DxJlKaHJ4gQ0DJGBa0SUIAZAzQf7D5cwqIBZDFwSBqwwQjdzoEgwQb+SgC8IAvvizBWIddEEQwBd/exiwGMgIxGZAnM0AkbwBxDJALA/E0UC8Eir+BKZhFIwCBgCr9h2EwjrI8AAAAABJRU5ErkJggg==>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAsAAAAbCAYAAACqenW9AAAAnklEQVR4XmNgGAWDHjADsQwQu6NLIANGIE4A4jlAzAkVuwvE/xkgmlGAKxD/BWIxJLFWBohibiQxMAAJPkcTOw0VRwEcUMGtaOJvoRgFSDJAFIOsRQYgscNoYmAPfANiUyQxHgaI4mgGiCFwg/gZMBUHI4ntAmIXJDmGGiD+B8TvgPgYECsA8S8o3wyhDAFAVgszQMIcxgf5ZxTQGQAADBAeDw5iyBwAAAAASUVORK5CYII=>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAkAAAAaCAYAAABl03YlAAAAvUlEQVR4XmNgGLxAAIglgTgEiM3R5OBAGIjNgPgfELugyaEAGyB+DsRK6BIwwAjES4G4FV0CGYgA8VUg9kSXQAbRQPwfiHcC8Usg3gDEx4BYBlnRHKiiRiDmhIr9BOLNcBVA8BaKkcFDBohGOABxTiMLMEA0wRVxQzkgdyEDkBgoSMBAEIi/AbEpXJqBgYcBomg5TIAFiL8CsTGUzwrE84G4jAESfnAAio5KqIIGKB/ExgAgK+QYcEiOAsIAAJYyIV9S2WfcAAAAAElFTkSuQmCC>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACIAAAAaCAYAAADSbo4CAAABjUlEQVR4Xu2UvyuFURjHH2GQSUSKJAySDCZFWW75A2z8CSaLwaL8A5JJyiSRzWIyGFFG5U4WA0kpgwjfr+c9ed7n3vOeW8qg91Of7j3nOT+ec95zjkhJye/4gBu+8q+Zg5+ZTS4WoxP2wXfRfgOw17gAT+EjHM36FNIGT+CL6IBj+XCSsIB6cOxb0cSSHMMdOCmazB0czrWI0yGaxIUPGPakwV1+glOwBe6LDryeaxFnQrQ9FxIYh4emvGn+R5kRTSLAZIq22sMEnkUTCtzAFVNO0iqaOSe3vIomMujqPfws/CRsz+3fhgfwDU6bdkn4GewWBrhLHLwK+13MwlvBhPkb4OKOpHZxhdyLTurhSecB5iRLLmbZFW1jryYP5bIpD8F2U66BN6TiKw1MJnVWwnWPwU977SstzHpLdLIi+NJyom4fyEglypvH9ykKk+CV5eEq8lJ0onPRV9TSlcXqvR9cKHebu9HjYjke5Gc1jbr43VOkGc7C1az+DI6Ivpysn4dXWWyNHUpKSkr+NV9O1V4lj6jiEAAAAABJRU5ErkJggg==>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAaCAYAAADxNd/XAAACQElEQVR4Xu2WwUtVQRSHj6Rg5MJQkiARMxci0sJVoGBSkIukRYtA927ChSAu3Aj+AyIhEYGrCKNdBK5cuCyhVQS6CsRFEULQIgrtfJ4ZPG98976HdEXhfvDj3pkzd945c2bOPJGSkpI8DlRLaedF4YHqMKghsWXRprqh+iv2XZfqutOEakP1Q9UXvimEy6p11S8xR/orzTWJgVeDub+KBVQY71QvVYNiQeypblWMyOaqmPMfU4PjldSf1VOxr7qjalS9FnNosWJENrfFxrMAkQHVG9dedu//nWEx5yMEkbclUnD8p1ggkW3VnGsXRpPYSuG057dYAN1Jfwrbh63DeLbJC9Wa6o9qyI0rDLaLT3WErODUjqozsXmoMgTKM8KivJWTi9IiNo6qFatUq7NzRthqK+G9Lr6JOZtC5eBg49zTxOZZFRvjSyQ/PuPaPaorYg7HrRkVzwZ25mIeKuD90J8LFSdvIEHUOgux7GbBFvwS3h+6frL03LWZZyq8k6GbzlYVVumZmJN5cDPj4LXUEKgVIJWM+wV8lnB21rXjmSFLza4/E5yndHLo8rQl5uAHsVvX0x5s1eo/C0R2Wf2OxMbqP3FtzgbzxDJ8VzV+bK7Odzm5H2tp8uhLkUuqEdV86N9U9YqtHv2PVZ+CbYEPEijZPhsEQKbvhTbzvJc6M3HWkLXPYk57OAOcSSCAwv96nBYuOy69tMRSsuO9ca4zMCa2tVJGVbuq6fCs+x44azjAI2lngLvgkeRfnCUlJRedf3iAetZApDGoAAAAAElFTkSuQmCC>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAaCAYAAADxNd/XAAACSklEQVR4Xu2WvWsWQRDGHzGCoilEUYQESaKIiChYiGAgRRKEEAuxUsF/wMpCCxshWGglIhYiiIVIgl0QBCUkpksC6RS0kDQWCSIIFqKoz+Psmrl97yN+HFG5Hzzc7c7e+87M7swd0NDQUMYX6no6+a9wjPoatCaxFbGF6qA+w57bSe1wOk1NUG+pveGZWthAPaY+wBzZlzVXEgPPQ7+9AAuoNsapO9QhWBBvqF2ZFcVshjk/mxoc97HyXf0l3lFHqDbqAcyhkcyKYg7A1isBkf3UmBvfcPd/nF6Y8xEFUXYkUuT4e1ggkZfURTeujXWwTMlpz0dYAF3JfIqOj46O1uuY3KZGqU/UUbeuNnRc/FZHtCty6hXVmdg86jIKVNeIkvIQrUkRe6hr1ClYcUdUH4epW9SQm69kEeZsin5chS3nziU2z13YGt8i5cx5N+6hNob759RBWH09+bECuEBNwdqydlJJqEQdZyCddCiIqlqIbbcIHcEX4V67pP8UClKObgpj32bbYYkp7Voy3kR2G/PQm1kObksNgaoAlWm9X4Q6UQxA3KO6qfXIBqCgVFeqr0LkvFqniq5MczAHZ2Db69kabHn9XwnS7ir722FOTaI1AI3leBpA5YtvCcvZW6nOfH8SWEv1UZfC/DNqN+wPNX+Smg+2y3oAVgNPkR+AAvzpAFaDK2gNQN9R6lZpANOwWvirOE71h3ud+0fhKvzHno5mrW/u3+E1rGWqbq66+RPBdhbWaks70GqiWhhE/stRTWI4XBsaGv5XvgHZ5X8HTNnS7wAAAABJRU5ErkJggg==>