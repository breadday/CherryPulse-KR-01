-- Use an explicit KST instant so the suite stays reproducible after 2026.
insert into cherrypulse_private.reservations(owner_id,id,details,original_details,execute_at,cancelled)
select 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',gen_random_uuid(),
 jsonb_build_object('date',to_char(local_time,'YYYY-MM-DD'),'time',to_char(local_time,'HH24:MI'),
 'type','지정가','qty',quantity,'price',price,'code',code),'{}',
 local_time at time zone 'Asia/Seoul',cancelled
from (values
 ('on_time',timestamp '2026-11-24 09:00',false,1,10),
 ('future',timestamp '2026-11-24 09:01',false,1,10),
 ('expired',timestamp '2026-11-24 08:58',false,1,10),
 ('cancelled',timestamp '2026-11-24 09:00',true,1,10),
 ('invalid_total',timestamp '2026-11-24 09:00',false,1000000000,1000000000),
 ('holiday',timestamp '2026-12-25 09:00',false,1,10)) f(code,local_time,cancelled,quantity,price);
